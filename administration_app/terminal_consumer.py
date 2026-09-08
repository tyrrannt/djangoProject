# terminal_consumer.py
"""WebSocket-потребитель для интерактивного терминала PTY (bash) управления сервером.

Обеспечивает полнофункциональный двунаправленный терминал с эмуляцией xterm-256color,
поддержкой интерактивных утилит (htop, top, vim, nano, journalctl), изменением размера
окна PTY (TIOCSWINSZ) и строгой проверкой прав суперпользователя.
"""

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import subprocess
import termios
from typing import Optional

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from core import logger


@database_sync_to_async
def _verify_superuser_access(user) -> tuple[bool, str]:
    """Асинхронно и потокобезопасно валидирует статус суперадминистратора в БД.

    Args:
        user: Объект пользователя Django из ASGI scope.

    Returns:
        tuple[bool, str]: Кортеж (is_superuser, username).
    """
    if not user:
        return False, "AnonymousUser"
    is_auth = getattr(user, "is_authenticated", False)
    if not is_auth:
        return False, str(user)
    is_super = bool(getattr(user, "is_superuser", False))
    username = getattr(user, "username", str(user))
    return is_super, username


class WebTerminalConsumer(AsyncWebsocketConsumer):
    """Асинхронный WebSocket-потребитель для управления PTY-сессией терминала Linux.

    Attributes:
        master_fd (Optional[int]): Файловый дескриптор master-конца псевдотерминала.
        pid (Optional[int]): Идентификатор процесса дочерней оболочки bash.
        loop (Optional[asyncio.AbstractEventLoop]): Цикл событий asyncio текущего потока.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Инициализирует экземпляр потребителя веб-терминала."""
        super().__init__(*args, **kwargs)
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> None:
        """Обрабатывает подключение WebSocket и запускает PTY-сессию оболочки bash.

        Выполняет строгую валидацию прав доступа: к терминалу допускаются исключительно
        аутентифицированные суперпользователи (is_superuser=True). При успешной проверке
        создается пара псевдотерминалов, запускается интерактивный bash в изолированной
        сессии (setsid) и регистрируется асинхронный callback чтения.

        Returns:
            None.
        """
        user = self.scope.get('user')
        client_ip = self.scope.get('client', ['unknown'])[0]
        is_super, username = await _verify_superuser_access(user)

        if not is_super:
            logger.warning(
                f"[WebTerminal] Попытка несанкционированного подключения к терминалу: user={username}, "
                f"ip={client_ip}"
            )
            await self.close(code=4003)
            return

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

            # Определяем стартовую рабочую директорию
            working_dir = "/"
            for candidate_dir in [
                os.environ.get("HOME", ""),
                "/home/proxmox/djangoProject",
                "/home/agy/djangoProject",
                "/home/proxmox",
                "/home/agy",
                os.getcwd(),
                "/root",
            ]:
                if candidate_dir and os.path.isdir(candidate_dir):
                    working_dir = candidate_dir
                    break

            # Запускаем интерактивную оболочку bash в собственной группе процессов
            proc = subprocess.Popen(
                ["/bin/bash", "--login"],
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

            # Регистрируем callback для неблокирующего чтения вывода из master_fd
            self.loop.add_reader(self.master_fd, self._pty_read_callback)
            logger.info(
                f"[WebTerminal] Успешно запущена сессия терминала для суперпользователя '{username}' "
                f"(PID: {self.pid}, CWD: {working_dir}, IP: {client_ip})"
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

        Returns:
            None.
        """
        if self.master_fd is None:
            return

        try:
            data = os.read(self.master_fd, 8192)
            if data:
                text = data.decode("utf-8", errors="replace")
                if self.loop and not self.loop.is_closed():
                    self.loop.create_task(self._async_send_output(text))
            else:
                # EOF: дочерний процесс завершил работу (например, по команде exit / Ctrl+D)
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

        Поддерживает как передачу структурированных JSON-сообщений (например, события resize
        для адаптации геометрии псевдотерминала через ioctl TIOCSWINSZ), так и прямой поток
        символов ввода.

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
            if text_data.startswith('{') and text_data.endswith('}'):
                try:
                    msg = json.loads(text_data)
                    if isinstance(msg, dict):
                        msg_type = msg.get("type")
                        if msg_type == "resize":
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
        """Корректно завершает WebSocket соединение и освобождает ресурсы PTY.

        Args:
            close_code (int): Код закрытия WebSocket-соединения.

        Returns:
            None.
        """
        logger.info(f"[WebTerminal] Отключение сессии терминала (PID: {self.pid}, close_code: {close_code})")
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
                # Посылаем сигнал завершения всей группе процессов
                pgid = os.getpgid(self.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as ex:
                logger.debug(f"[WebTerminal] Завершение процесса PID {self.pid}: {ex}")
            self.pid = None
