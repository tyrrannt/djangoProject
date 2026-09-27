# terminal_consumer.py
"""WebSocket-потребитель для интерактивного терминала PTY (bash / tmux) управления сервером.

Обеспечивает полнофункциональный двунаправленный терминал с эмуляцией xterm-256color,
поддержкой интерактивных утилит (htop, top, vim, nano, journalctl), изменением размера
окна PTY (TIOCSWINSZ), инкрементальным декодированием UTF-8, поддержкой устойчивых
сессий tmux, мультивкладочностью и сквозным аудитом подключений в БД.
"""

import asyncio
import codecs
import fcntl
import json
import os
import pty
import shutil
import signal
import struct
import subprocess
import termios
import urllib.parse
from typing import Optional, Tuple, Dict, Any

from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from core import logger


@database_sync_to_async
def _verify_superuser_access(user) -> Tuple[bool, str]:
    """Асинхронно и потокобезопасно валидирует статус суперадминистратора в БД.

    Args:
        user: Объект пользователя Django из ASGI scope.

    Returns:
        Tuple[bool, str]: Кортеж (is_superuser, username).
    """
    if not user:
        return False, "AnonymousUser"
    is_auth = getattr(user, "is_authenticated", False)
    if not is_auth:
        return False, str(user)
    is_super = bool(getattr(user, "is_superuser", False))
    username = getattr(user, "username", str(user))
    return is_super, username


@database_sync_to_async
def _create_terminal_session_audit(
    user,
    ip_address: str,
    user_agent: str,
    tab_id: str,
    is_tmux: bool,
) -> Optional[int]:
    """Фиксирует факт открытия сессии веб-терминала в базе данных.

    Args:
        user: Объект аутентифицированного пользователя Django.
        ip_address (str): IP-адрес клиентского подключения.
        user_agent (str): Строка User-Agent браузера клиента.
        tab_id (str): Идентификатор вкладки терминала.
        is_tmux (bool): Флаг использования устойчивой сессии tmux.

    Returns:
        Optional[int]: Идентификатор созданной записи WebTerminalSession или None.
    """
    try:
        from administration_app.models import WebTerminalSession

        session = WebTerminalSession.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            ip_address=ip_address,
            user_agent=user_agent[:512],
            tab_id=tab_id[:32],
            is_tmux=is_tmux,
        )
        return session.pk
    except Exception as ex:
        logger.error(f"[WebTerminal] Ошибка логирования сессии в БД: {ex}")
        return None


@database_sync_to_async
def _close_terminal_session_audit(session_pk: Optional[int], close_code: int) -> None:
    """Фиксирует завершение сессии веб-терминала и вычисляет ее длительность.

    Args:
        session_pk (Optional[int]): Идентификатор записи WebTerminalSession.
        close_code (int): WebSocket код закрытия соединения.
    """
    if not session_pk:
        return
    try:
        from administration_app.models import WebTerminalSession
        from django.utils import timezone

        session = WebTerminalSession.objects.filter(pk=session_pk).first()
        if session:
            session.ended_at = timezone.now()
            session.close_code = close_code
            session.calculate_duration()
            session.save(update_fields=["ended_at", "close_code", "duration_seconds"])
    except Exception as ex:
        logger.error(f"[WebTerminal] Ошибка обновления сессии в БД: {ex}")


class WebTerminalConsumer(AsyncWebsocketConsumer):
    """Асинхронный WebSocket-потребитель для управления PTY-сессией терминала Linux.

    Поддерживает устойчивые сессии tmux, мультивкладочность, пинг-понг задержки,
    инкрементальный потоковый UTF-8 парсинг и аудит в БД.

    Attributes:
        master_fd (Optional[int]): Файловый дескриптор master-конца псевдотерминала.
        pid (Optional[int]): Идентификатор процесса дочерней оболочки.
        loop (Optional[asyncio.AbstractEventLoop]): Цикл событий asyncio текущего потока.
        decoder (codecs.IncrementalDecoder): Инкрементальный декодер потока UTF-8.
        session_pk (Optional[int]): Первичный ключ сессии аудита в БД.
        is_tmux (bool): Признак подключения через сессию tmux.
        tab_id (str): Идентификатор вкладки терминала.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Инициализирует экземпляр потребителя веб-терминала."""
        super().__init__(*args, **kwargs)
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.decoder: codecs.IncrementalDecoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.session_pk: Optional[int] = None
        self.is_tmux: bool = False
        self.tab_id: str = "tab_1"

    async def connect(self) -> None:
        """Обрабатывает подключение WebSocket и запускает PTY-сессию оболочки bash/tmux.

        Выполняет строгую валидацию прав доступа: к терминалу допускаются исключительно
        аутентифицированные суперпользователи (is_superuser=True). При успешной проверке
        создается пара псевдотерминалов, запускается интерактивный процесс в изолированной
        сессии (setsid), регистрируется запись аудита и callback чтения.

        Returns:
            None.
        """
        user = self.scope.get("user")
        client = self.scope.get("client", ["127.0.0.1"])
        client_ip = client[0] if client else "127.0.0.1"

        headers = dict(self.scope.get("headers", []))
        user_agent = headers.get(b"user-agent", b"").decode("utf-8", errors="ignore")

        is_super, username = await _verify_superuser_access(user)

        if not is_super:
            logger.warning(
                f"[WebTerminal] Попытка несанкционированного подключения к терминалу: user={username}, "
                f"ip={client_ip}"
            )
            await self.close(code=4003)
            return

        # Разбор параметров запроса (вкладка и режим tmux)
        query_string = self.scope.get("query_string", b"").decode("utf-8", errors="ignore")
        params = urllib.parse.parse_qs(query_string)
        self.tab_id = params.get("tab_id", ["tab_1"])[0]
        use_tmux_param = params.get("use_tmux", ["0"])[0].lower()
        use_tmux = use_tmux_param in ("1", "true", "yes")

        await self.accept()
        self.loop = asyncio.get_running_loop()

        try:
            # Создаем пару псевдотерминалов (master/slave)
            self.master_fd, slave_fd = pty.openpty()

            # Устанавливаем неблокирующий режим для master_fd
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Формируем переменные окружения сессии терминала
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["LANG"] = "ru_RU.UTF-8"
            env["LC_ALL"] = "ru_RU.UTF-8"

            # Определяем стартовую рабочую директорию (с сохранением продакшн-пути /home/proxmox/djangoProject)
            working_dir = "/"
            candidate_dirs = [
                str(settings.BASE_DIR) if getattr(settings, "BASE_DIR", None) else "",
                "/home/proxmox/djangoProject",
                "/home/agy/djangoProject",
                os.environ.get("HOME", ""),
                "/home/proxmox",
                "/home/agy",
                os.getcwd(),
                "/root",
            ]
            for candidate_dir in candidate_dirs:
                if candidate_dir and os.path.isdir(candidate_dir):
                    working_dir = candidate_dir
                    break

            # Формируем команду запуска оболочки
            tmux_bin = shutil.which("tmux")
            if use_tmux and tmux_bin:
                clean_user = "".join(c for c in username if c.isalnum() or c in ("_", "-")) or "admin"
                clean_tab = "".join(c for c in self.tab_id if c.isalnum() or c in ("_", "-")) or "tab_1"
                session_name = f"barkol_{clean_user}_{clean_tab}"
                cmd = [tmux_bin, "new-session", "-A", "-s", session_name]
                self.is_tmux = True
            else:
                cmd = ["/bin/bash", "--login"]
                self.is_tmux = False

            # Запускаем интерактивную оболочку в собственной группе процессов
            proc = subprocess.Popen(
                cmd,
                preexec_fn=os.setsid,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=working_dir,
                env=env,
                close_fds=True,
            )
            os.close(slave_fd)
            self.pid = proc.pid

            # Фиксируем сессию в базе данных
            self.session_pk = await _create_terminal_session_audit(
                user=user,
                ip_address=client_ip,
                user_agent=user_agent,
                tab_id=self.tab_id,
                is_tmux=self.is_tmux,
            )

            # Регистрируем callback для неблокирующего чтения вывода из master_fd
            self.loop.add_reader(self.master_fd, self._pty_read_callback)
            logger.info(
                f"[WebTerminal] Успешно запущена сессия терминала для суперпользователя '{username}' "
                f"(PID: {self.pid}, CWD: {working_dir}, IP: {client_ip}, tmux={self.is_tmux}, tab={self.tab_id})"
            )

        except Exception as ex:
            logger.error(f"[WebTerminal] Критическая ошибка запуска PTY сессии: {ex}", exc_info=True)
            try:
                await self.send(text_data=f"\r\n\x1b[31;1m[ОШИБКА] Не удалось инициализировать PTY: {ex}\x1b[0m\r\n")
            except Exception:
                pass
            await self.close()

    async def _async_send_output(self, text: str) -> None:
        """Безопасно пересылает текстовые данные в открытый WebSocket сокет.

        Args:
            text (str): Текстовый вывод от псевдотерминала.
        """
        try:
            await self.send(text_data=text)
        except Exception as e:
            logger.debug(f"[WebTerminal] Сокет закрыт при отправке данных: {e}")

    def _pty_read_callback(self) -> None:
        """Callback-функция для чтения данных из PTY и пересылки в WebSocket клиент.

        Вызывается циклом событий asyncio при появлении доступных данных в master_fd.
        Использует инкрементальный UTF-8 декодер для предотвращения повреждения кириллических символов.

        Returns:
            None.
        """
        if self.master_fd is None:
            return

        try:
            data = os.read(self.master_fd, 8192)
            if data:
                text = self.decoder.decode(data)
                if text and self.loop and not self.loop.is_closed():
                    self.loop.create_task(self._async_send_output(text))
            else:
                # EOF: дочерний процесс завершил работу (например, по команде exit / Ctrl+D)
                final_text = self.decoder.decode(b"", final=True)
                if final_text and self.loop and not self.loop.is_closed():
                    self.loop.create_task(self._async_send_output(final_text))
                self._cleanup()
                if self.loop and not self.loop.is_closed():
                    self.loop.create_task(self.close())
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            self._cleanup()
            if self.loop and not self.loop.is_closed():
                self.loop.create_task(self.close())
        except Exception as e:
            logger.error(f"[WebTerminal] Ошибка чтения из master_fd: {e}")
            self._cleanup()
            if self.loop and not self.loop.is_closed():
                self.loop.create_task(self.close())

    async def receive(self, text_data: Optional[str] = None, bytes_data: Optional[bytes] = None) -> None:
        """Принимает команды, ввод с клавиатуры и управляющие сигналы от клиента xterm.js.

        Поддерживает передачу управляющих JSON-сообщений (resize, ping, input) и прямой поток ввода.

        Args:
            text_data (Optional[str]): Текстовые данные или JSON-сообщение от клиента.
            bytes_data (Optional[bytes]): Бинарные данные от клиента.

        Returns:
            None.
        """
        if self.master_fd is None:
            return

        if text_data:
            # Проверяем, является ли сообщение управляющей JSON-командой
            if text_data.startswith("{") and text_data.endswith("}"):
                try:
                    msg = json.loads(text_data)
                    if isinstance(msg, dict):
                        msg_type = msg.get("type")
                        if msg_type == "ping":
                            # Ответ на heartbeat для замера задержки сети (latency RTT)
                            await self.send(
                                text_data=json.dumps({
                                    "type": "pong",
                                    "timestamp": msg.get("timestamp"),
                                })
                            )
                            return
                        elif msg_type == "resize":
                            cols = int(msg.get("cols", 80))
                            rows = int(msg.get("rows", 24))
                            winsize = struct.pack("HHHH", rows, cols, 0, 0)
                            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
                            return
                        elif msg_type == "input":
                            input_payload = msg.get("data", "")
                            os.write(self.master_fd, input_payload.encode("utf-8", errors="replace"))
                            return
                except (json.JSONDecodeError, ValueError, TypeError, OSError):
                    pass

            # Прямая запись строкового ввода в PTY
            try:
                os.write(self.master_fd, text_data.encode("utf-8", errors="replace"))
            except Exception as ex:
                logger.error(f"[WebTerminal] Ошибка записи в master_fd: {ex}")

        elif bytes_data:
            try:
                os.write(self.master_fd, bytes_data)
            except Exception as ex:
                logger.error(f"[WebTerminal] Ошибка записи байт в master_fd: {ex}")

    async def disconnect(self, close_code: int) -> None:
        """Корректно завершает WebSocket соединение, логирует длительность и освобождает ресурсы PTY.

        Args:
            close_code (int): Код закрытия WebSocket-соединения.

        Returns:
            None.
        """
        logger.info(
            f"[WebTerminal] Отключение сессии терминала (PID: {self.pid}, close_code: {close_code}, "
            f"session_pk: {self.session_pk})"
        )
        if self.session_pk:
            await _close_terminal_session_audit(self.session_pk, close_code)
        self._cleanup()

    def _cleanup(self) -> None:
        """Очищает дескрипторы, удаляет обработчик чтения из event loop и завершает процесс bash.

        Returns:
            None.
        """
        if self.master_fd is not None:
            if self.loop is not None:
                try:
                    self.loop.remove_reader(self.master_fd)
                except Exception:
                    pass
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        if self.pid is not None:
            try:
                # Посылаем сигнал завершения процессу (или клиенту tmux)
                pgid = os.getpgid(self.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as ex:
                logger.debug(f"[WebTerminal] Завершение процесса PID {self.pid}: {ex}")
            self.pid = None
