import base64
import email
from email.header import Header, decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, getaddresses, make_msgid, parseaddr, parsedate_to_datetime
import imaplib
import logging
import re
import ssl
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


def format_imap_date(d: date) -> str:
    """Форматирует дату по стандарту RFC 3501 (dd-Mon-yyyy) с английскими названиями месяцев.

    Args:
        d (date): Объект даты.

    Returns:
        str: Строка вида '02-Sep-2026'.
    """
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{d.day:02d}-{months[d.month - 1]}-{d.year}"


def invalidate_mailbox_cache(email_addr: str) -> None:
    """Сбрасывает кэш папок и списков писем для указанного почтового ящика.

    Args:
        email_addr (str): Email адрес ящика.
    """
    if email_addr:
        addr = email_addr.strip().lower()
        cache.delete(f"mailbox_folders_{addr}")
        ver_key = f"mailbox_ver_{addr}"
        try:
            cache.incr(ver_key)
        except Exception:
            cache.set(ver_key, int(time.time()), timeout=86400 * 30)



def decode_imap_utf7(encoded_name: str) -> str:
    """Декодирует имя папки IMAP из модифицированного UTF-7 в Unicode.

    Args:
        encoded_name (str): Закодированное имя папки IMAP (например, '&BB4EQgQ,-').

    Returns:
        str: Декодированное человекочитаемое имя папки.
    """
    try:
        def _replace_part(match):
            sub = match.group(1)
            if not sub:
                return "&"
            padding = "=" * ((4 - len(sub) % 4) % 4)
            b64_str = (sub + padding).replace(",", "/")
            import base64
            decoded_bytes = base64.b64decode(b64_str)
            return decoded_bytes.decode("utf-16-be")

        return re.sub(r"&([A-Za-z0-9+,]*)-", _replace_part, encoded_name)
    except Exception as e:
        logger.debug(f"[IMAP] Ошибка декодирования UTF-7 для {encoded_name}: {e}")
        return encoded_name


def encode_imap_utf7(folder_name: str) -> str:
    """Кодирует имя папки Unicode в формат IMAP modified UTF-7.

    Args:
        folder_name (str): Имя папки в Unicode.

    Returns:
        str: Закодированная строка для отправки серверу IMAP.
    """
    try:
        def _replace_part(match):
            text = match.group(0)
            if text == "&":
                return "&-"
            import base64
            b64 = base64.b64encode(text.encode("utf-16-be")).decode("ascii")
            return "&" + b64.rstrip("=").replace("/", ",") + "-"

        return re.sub(r"[^\x20-\x7e]+|&", _replace_part, folder_name)
    except Exception:
        return folder_name


def decode_str(header_value: Optional[str]) -> str:
    """Декодирует MIME-заголовок (тему, отправителя) в Unicode строку.

    Args:
        header_value (str, optional): Сырой заголовок из email.

    Returns:
        str: Декодированный текст.
    """
    if not header_value:
        return ""
    try:
        decoded_fragments = decode_header(header_value)
        result = []
        for text, encoding in decoded_fragments:
            if isinstance(text, bytes):
                if encoding:
                    try:
                        result.append(text.decode(encoding, errors="replace"))
                    except Exception:
                        result.append(text.decode("utf-8", errors="replace"))
                else:
                    result.append(text.decode("utf-8", errors="replace"))
            else:
                result.append(str(text))
        return "".join(result)
    except Exception as e:
        logger.debug(f"[IMAP] Ошибка декодирования заголовка: {e}")
        return str(header_value)


class ImapMailService:
    """Сервис для подключения к почтовому ящику по протоколу IMAP."""

    def __init__(self, host: str, port: int, email_addr: str, password: str, use_ssl: bool = True):
        """Инициализирует сервис с параметрами подключения.

        Args:
            host (str): IMAP хост (например, 'imap.barkol.ru').
            port (int): IMAP порт (например, 993).
            email_addr (str): Email адрес / логин.
            password (str): Пароль учетной записи.
            use_ssl (bool): Использовать ли SSL-соединение.
        """
        self.host = host
        self.port = port
        self.email = email_addr or ""
        self.email_addr = email_addr or ""
        self.password = password
        self.use_ssl = use_ssl
        self.client: Optional[imaplib.IMAP4] = None

    def connect(self) -> bool:
        """Устанавливает соединение с IMAP сервером и авторизуется.

        Автоматически проверяет различные форматы логина (полный email и короткое имя),
        а также валидирует наличие пароля.

        Returns:
            bool: True в случае успешного входа, иначе False.

        Raises:
            ValueError: Если пароль пустой.
            PermissionError / Exception: При ошибке авторизации.
        """
        if not self.password:
            raise ValueError(
                "Пароль от корпоративной почты не задан в профиле пользователя или настройках почтового ящика."
            )

        logins_to_try = [self.email.strip()]
        if "@" in self.email:
            short_user = self.email.split("@")[0].strip()
            if short_user and short_user not in logins_to_try:
                logins_to_try.append(short_user)
        else:
            full_user = f"{self.email.strip()}@barkol.ru"
            if full_user not in logins_to_try:
                logins_to_try.append(full_user)

        last_error = None
        for login_candidate in logins_to_try:
            try:
                if self.use_ssl:
                    ssl_context = ssl.create_default_context()
                    clean_host = (self.host or "").strip()
                    # Если подключение идет напрямую по IP адресу (например, 192.168.10.242)
                    if clean_host.replace(".", "").isdigit():
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                    self.client = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ssl_context, timeout=10.0)
                else:
                    self.client = imaplib.IMAP4(self.host, self.port, timeout=10.0)

                status, response = self.client.login(login_candidate, self.password)
                if status == "OK":
                    return True
            except Exception as err:
                last_error = err
                try:
                    if self.client:
                        self.client.logout()
                except Exception:
                    pass
                self.client = None

        if last_error:
            raise last_error
        return False

    def close(self) -> None:
        """Безопасно и быстро закрывает соединение с сервером без зависания."""
        if self.client:
            try:
                # Ограничиваем таймаут сокета перед logout до 2 секунд, чтобы не блокировать Gunicorn
                if hasattr(self.client, "sock") and self.client.sock:
                    try:
                        self.client.sock.settimeout(2.0)
                    except Exception:
                        pass
                self.client.logout()
            except Exception:
                pass
            finally:
                try:
                    if hasattr(self.client, "sock") and self.client.sock:
                        self.client.sock.close()
                except Exception:
                    pass
                self.client = None

    def __enter__(self):
        """Контекстный менеджер входа."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер выхода."""
        self.close()

    def get_folders(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Возвращает список всех папок почтового ящика со статистикой сообщений и иерархической структурой.

        Args:
            force_refresh (bool): Принудительно запросить данные с IMAP сервера в обход кэша.

        Returns:
            list[dict]: Список словарей папок с полями raw_name, display_name, full_path_display, level, unseen, total, icon, type.
        """
        cache_key = f"mailbox_folders_{self.email_addr.strip().lower()}" if self.email_addr else None
        if cache_key and not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data

        if not self.client:
            return []

        status, folder_list = self.client.list()
        if status != "OK" or not folder_list:
            return []

        parsed_folders = []
        for folder_item in folder_list:
            if not folder_item:
                continue
            line = folder_item.decode("latin-1") if isinstance(folder_item, bytes) else folder_item
            match = re.search(r'\((?P<flags>[^\)]*)\)\s+"(?P<delimiter>[^"]+)"\s+"?(?P<name>[^"]+)"?', line)
            if not match:
                continue

            flags_str = match.group("flags").lower()
            delimiter = match.group("delimiter") or "/"
            raw_name = match.group("name").strip('"')

            # Пропускаем папки \NoSelect и системные PIM-папки Kerio Connect (контакты, календарь, заметки)
            if "\\noselect" in flags_str or "\\nonexistent" in flags_str:
                continue

            # Разбиваем путь папки по разделителю иерархии
            raw_parts = [p for p in raw_name.split(delimiter) if p]
            if not raw_parts:
                raw_parts = [raw_name]

            decoded_parts = [decode_imap_utf7(p) for p in raw_parts]
            level = len(raw_parts) - 1
            leaf_display = decoded_parts[-1]
            root_raw = raw_parts[0]
            root_decoded = decoded_parts[0]
            lower_root = root_decoded.lower()

            if lower_root in ["contacts", "calendar", "tasks", "notes", "контакты", "календарь", "задачи", "заметки"]:
                continue

            # Определяем тип корневой группы папок
            root_type = "custom"
            if root_raw.upper() == "INBOX" or lower_root in ("inbox", "входящие") or "\\inbox" in flags_str:
                root_type = "inbox"
            elif "\\sent" in flags_str or lower_root in ("sent", "sent items", "sent messages", "отправленные", "отправленные сообщения"):
                root_type = "sent"
            elif "\\drafts" in flags_str or lower_root in ("drafts", "draft", "черновики"):
                root_type = "drafts"
            elif "\\trash" in flags_str or lower_root in ("trash", "deleted", "deleted items", "deleted messages", "корзина", "удаленные"):
                root_type = "trash"
            elif "\\junk" in flags_str or lower_root in ("spam", "junk", "junk email", "спам"):
                root_type = "spam"
            elif "\\important" in flags_str or "\\flagged" in flags_str or lower_root in ("important", "важные"):
                root_type = "important"

            # Определяем свойства текущей папки
            if level == 0:
                folder_type = root_type
                if folder_type == "inbox":
                    display_name = "Входящие"
                    icon = "bx bx-inbox"
                elif folder_type == "sent":
                    display_name = "Отправленные"
                    icon = "bx bx-paper-plane"
                elif folder_type == "drafts":
                    display_name = "Черновики"
                    icon = "bx bx-edit"
                elif folder_type == "trash":
                    display_name = "Корзина"
                    icon = "bx bx-trash"
                elif folder_type == "spam":
                    display_name = "Спам"
                    icon = "bx bx-error"
                elif folder_type == "important":
                    display_name = "Важные"
                    icon = "bx bx-star"
                else:
                    display_name = leaf_display
                    icon = "bx bx-folder"
                full_path_display = display_name
            else:
                # Вложенная подпапка (сохраняет свое индивидуальное имя и иерархию!)
                folder_type = "subfolder"
                display_name = leaf_display
                icon = "bx bx-folder"
                first_name = "Входящие" if root_type == "inbox" else decoded_parts[0]
                full_path_display = " / ".join([first_name] + decoded_parts[1:])

            # Получаем количество непрочитанных и всего писем
            # Опрашиваем статус по сети ТОЛЬКО для Входящих (INBOX), чтобы исключить проблему
            # N+1 сетевых запросов (20-30 последовательных вызовов STATUS к удаленному серверу)
            unseen_count = 0
            total_count = 0
            if root_type == "inbox" or len(folder_list) <= 3:
                try:
                    status_res, status_data = self.client.status(f'"{raw_name}"', "(UNSEEN MESSAGES)")
                    if status_res == "OK" and status_data:
                        stat_line = status_data[0].decode("latin-1")
                        unseen_m = re.search(r"UNSEEN\s+(\d+)", stat_line)
                        total_m = re.search(r"MESSAGES\s+(\d+)", stat_line)
                        if unseen_m:
                            unseen_count = int(unseen_m.group(1))
                        if total_m:
                            total_count = int(total_m.group(1))
                except Exception:
                    pass

            parsed_folders.append({
                "raw_name": raw_name,
                "display_name": display_name,
                "full_path_display": full_path_display,
                "unseen": unseen_count,
                "total": total_count,
                "icon": icon,
                "type": folder_type,
                "root_type": root_type,
                "level": level,
                "is_subfolder": level > 0,
                "delimiter": delimiter,
                "raw_parts": raw_parts,
                "decoded_parts": decoded_parts,
            })

        # Иерархическая сортировка дерева папок:
        # Входящие и все вложенные папки Входящих -> Отправленные -> Черновики -> Корзина -> Спам -> Пользовательские
        order_priority = {"inbox": 1, "sent": 2, "drafts": 3, "trash": 4, "spam": 5, "important": 6, "custom": 10}

        def sort_key(f):
            prio = order_priority.get(f["root_type"], 99)
            path_tuple = tuple(p.lower() for p in f["decoded_parts"])
            return (prio, path_tuple)

        parsed_folders.sort(key=sort_key)

        if cache_key:
            cache.set(cache_key, parsed_folders, timeout=1800)  # Кэшируем дерево папок на 30 минут

        return parsed_folders

    def get_messages(
        self,
        folder_name: str = "INBOX",
        page: int = 1,
        per_page: int = 25,
        query: Optional[str] = None,
        sort_by: str = "date",
        sort_dir: str = "desc",
        filter_by: str = "all",
        force_refresh: bool = False,
        q_scope: str = "all",
        date_range: str = "all",
        date_from: str = "",
        date_to: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Возвращает страницу списка писем с полнотекстовым поиском (включая тело BODY) и фильтрацией по датам.

        Args:
            folder_name (str): Имя папки IMAP.
            page (int): Номер страницы (1-based).
            per_page (int): Количество писем на страницу.
            query (str, optional): Поисковая строка.
            sort_by (str): Поле сортировки ('date', 'from', 'subject', 'size', 'flagged', 'unread', 'attachments').
            sort_dir (str): Направление ('asc' или 'desc').
            filter_by (str): Фильтр ('all', 'unread', 'flagged', 'attachments').
            force_refresh (bool): Принудительный запрос в обход кэша.
            q_scope (str): Область поиска ('all' - везде включая тело, 'headers' - тема и автор, 'body' - только текст).
            date_range (str): Диапазон дат ('all', 'today', 'week', 'month', 'custom').
            date_from (str): Начальная дата диапазона (ГГГГ-ММ-ДД).
            date_to (str): Конечная дата диапазона (ГГГГ-ММ-ДД).

        Returns:
            tuple[list[dict], int]: (Список превью писем, общее количество писем).
        """
        email_clean = (self.email_addr or "").strip().lower()
        ver_key = f"mailbox_ver_{email_clean}"
        cache_ver = cache.get(ver_key) or 1
        q_scope = (q_scope or "all").lower()
        date_range = (date_range or "all").lower()
        cache_key = f"mailbox_msgs_v3_{email_clean}_{cache_ver}_{folder_name}_{page}_{per_page}_{sort_by}_{sort_dir}_{filter_by}_{query or ''}_{q_scope}_{date_range}_{date_from}_{date_to}"

        if not force_refresh and email_clean:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data

        if not self.client:
            return [], 0

        status, _ = self.client.select(f'"{folder_name}"', readonly=True)
        if status != "OK":
            return [], 0

        sort_by = (sort_by or "date").lower()
        sort_dir = (sort_dir or "desc").lower()
        filter_by = (filter_by or "all").lower()

        # Фильтрация по датам (RFC 3501 SINCE / BEFORE)
        date_criteria_parts = []
        now_date = datetime.now().date()
        if date_range == "today":
            date_criteria_parts.append(f"SINCE {format_imap_date(now_date)}")
        elif date_range == "week":
            week_ago = now_date - timedelta(days=7)
            date_criteria_parts.append(f"SINCE {format_imap_date(week_ago)}")
        elif date_range == "month":
            month_ago = now_date - timedelta(days=30)
            date_criteria_parts.append(f"SINCE {format_imap_date(month_ago)}")
        elif date_range == "custom":
            if date_from:
                try:
                    d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
                    date_criteria_parts.append(f"SINCE {format_imap_date(d_from)}")
                except Exception:
                    pass
            if date_to:
                try:
                    d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
                    d_to_next = d_to + timedelta(days=1)
                    date_criteria_parts.append(f"BEFORE {format_imap_date(d_to_next)}")
                except Exception:
                    pass

        # Базовый критерий фильтрации
        criteria_list = []
        if filter_by == "unread" or sort_by == "unread":
            criteria_list.append("UNSEEN")
        elif filter_by == "flagged" or sort_by == "flagged":
            criteria_list.append("FLAGGED")

        if date_criteria_parts:
            criteria_list.extend(date_criteria_parts)

        base_criteria = " ".join(criteria_list) if criteria_list else "ALL"

        # Формирование критерия сортировки IMAP (RFC 5256) по реальному заголовку письма
        sort_field = "DATE"
        if sort_by == "from":
            sort_field = "FROM"
        elif sort_by == "subject":
            sort_field = "SUBJECT"
        elif sort_by == "size":
            sort_field = "SIZE"

        if sort_dir == "desc":
            sort_key = f"(REVERSE {sort_field})"
        else:
            sort_key = f"({sort_field})"

        uids_list = []

        # 1. Поиск сообщений по запросу
        if query:
            query_clean = query.strip()
            variants = list(dict.fromkeys([
                query_clean,
                query_clean.lower(),
                query_clean.capitalize(),
                query_clean.upper(),
                query_clean.title(),
            ]))

            found_uids = []
            for var in variants:
                try:
                    var_bytes = var.encode("utf-8")
                    if q_scope == "body":
                        search_atoms = ["BODY", var_bytes]
                    elif q_scope == "headers":
                        search_atoms = ["OR", "FROM", var_bytes, "SUBJECT", var_bytes]
                    else:
                        # По умолчанию: поиск везде (включая тело BODY)
                        search_atoms = ["TEXT", var_bytes]

                    base_args = [base_criteria] if base_criteria != "ALL" else []
                    full_sort_args = ["sort", sort_key, "UTF-8"] + base_args + search_atoms
                    status, sort_data = self.client.uid(*full_sort_args)

                    if status == "OK" and sort_data and sort_data[0]:
                        for uid_item in sort_data[0].split():
                            if uid_item and uid_item != b"0" and uid_item not in found_uids:
                                found_uids.append(uid_item)
                except Exception as e:
                    logger.debug(f"[IMAP] Поиск варианта '{var}' через UID SORT не удался: {e}")

            if not found_uids:
                for var in variants:
                    try:
                        var_bytes = var.encode("utf-8")
                        if q_scope == "body":
                            search_atoms = ["BODY", var_bytes]
                        elif q_scope == "headers":
                            search_atoms = ["OR", "FROM", var_bytes, "SUBJECT", var_bytes]
                        else:
                            search_atoms = ["TEXT", var_bytes]

                        base_args = [base_criteria] if base_criteria != "ALL" else []
                        full_search_args = ["search", "CHARSET", "UTF-8"] + base_args + search_atoms
                        status, search_data = self.client.uid(*full_search_args)

                        if status == "OK" and search_data and search_data[0]:
                            for uid_item in search_data[0].split():
                                if uid_item and uid_item != b"0" and uid_item not in found_uids:
                                    found_uids.append(uid_item)
                    except Exception:
                        pass

            if not found_uids:
                try:
                    for var in variants:
                        ascii_var = var.encode("ascii", errors="ignore").decode("ascii")
                        if not ascii_var:
                            continue
                        crit_prefix = f"{base_criteria} " if base_criteria != "ALL" else ""
                        if q_scope == "body":
                            search_crit = f'({crit_prefix}(BODY "{ascii_var}"))'
                        elif q_scope == "headers":
                            search_crit = f'({crit_prefix}(OR (FROM "{ascii_var}") (SUBJECT "{ascii_var}")))'
                        else:
                            search_crit = f'({crit_prefix}(TEXT "{ascii_var}"))'

                        status, search_data = self.client.uid("search", None, search_crit)
                        if status == "OK" and search_data and search_data[0]:
                            for uid_item in search_data[0].split():
                                if uid_item and uid_item != b"0" and uid_item not in found_uids:
                                    found_uids.append(uid_item)
                except Exception:
                    pass

            uids_list = found_uids
        else:
            # 2. Серверная сортировка писем
            is_fast_date_desc = (
                sort_by == "date"
                and sort_dir == "desc"
                and filter_by == "all"
                and date_range == "all"
                and not query
            )
            if is_fast_date_desc:
                # В протоколе IMAP UID писем возрастают строго монотонно.
                # Вызов UID SEARCH ALL выполняется почтовым сервером мгновенно (по индексу)
                # и избавляет удаленный сервер от парсинга и сортировки заголовков 10 000+ писем.
                try:
                    status, search_data = self.client.uid("search", None, "ALL")
                    if status == "OK" and search_data and search_data[0]:
                        raw_uids = [u for u in search_data[0].split() if u and u != b"0"]
                        raw_uids.reverse()  # Новые письма (с наибольшим UID) первыми
                        uids_list = raw_uids
                except Exception as e:
                    logger.debug(f"[IMAP] Fast UID SEARCH не удался: {e}")

            if not uids_list:
                # Серверная сортировка по реальной дате (RFC 5256 SORT) для кастомных фильтров
                try:
                    status, sort_data = self.client.uid("sort", sort_key, "UTF-8", base_criteria)
                    if status == "OK" and sort_data and sort_data[0]:
                        uids_list = [u for u in sort_data[0].split() if u and u != b"0"]
                except Exception as e:
                    logger.debug(f"[IMAP] UTF-8 UID SORT не удался, пробуем US-ASCII: {e}")
                    try:
                        status, sort_data = self.client.uid("sort", sort_key, "US-ASCII", base_criteria)
                        if status == "OK" and sort_data and sort_data[0]:
                            uids_list = [u for u in sort_data[0].split() if u and u != b"0"]
                    except Exception as e2:
                        logger.debug(f"[IMAP] US-ASCII UID SORT не удался: {e2}")

                # Fallback к обычному UID SEARCH, если сервер не поддерживает расширение SORT
                if not uids_list:
                    status, search_data = self.client.uid("search", None, base_criteria)
                    if status == "OK" and search_data and search_data[0]:
                        uids_list = [u for u in search_data[0].split() if u and u != b"0"]
                        if sort_dir == "desc":
                            uids_list.reverse()

        total_messages = len(uids_list)
        if total_messages == 0:
            if email_clean:
                cache.set(cache_key, ([], 0), timeout=180)
            return [], 0

        # Пагинация по UIDs
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_uids = uids_list[start_idx:end_idx]

        if not page_uids:
            if email_clean:
                cache.set(cache_key, ([], total_messages), timeout=180)
            return [], total_messages

        # 3. Высокоскоростной пакетный FETCH (все 25 писем за 1 сетевой запрос вместо 25)
        uids_ints = []
        for u in page_uids:
            u_str = u.decode("ascii") if isinstance(u, bytes) else str(u)
            if u_str.isdigit():
                uids_ints.append(int(u_str))

        if not uids_ints:
            return [], total_messages

        uids_sequence = ",".join(str(u) for u in uids_ints)
        messages_by_uid = {}

        try:
            fetch_status, fetch_data = self.client.uid(
                "fetch",
                uids_sequence,
                "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE MESSAGE-ID CONTENT-TYPE)])"
            )
            if fetch_status == "OK" and fetch_data:
                for item in fetch_data:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue

                    meta_line = item[0].decode("latin-1", errors="ignore") if isinstance(item[0], bytes) else str(item[0])
                    raw_headers = item[1]
                    if not raw_headers or not isinstance(raw_headers, bytes):
                        continue

                    uid_m = re.search(r"UID\s+(\d+)", meta_line, re.IGNORECASE)
                    if not uid_m:
                        continue
                    item_uid = int(uid_m.group(1))

                    is_seen = "\\seen" in meta_line.lower()
                    is_flagged = "\\flagged" in meta_line.lower()

                    size_m = re.search(r"RFC822\.SIZE\s+(\d+)", meta_line, re.IGNORECASE)
                    size_bytes = int(size_m.group(1)) if size_m else len(raw_headers)

                    # Извлечение даты получения на сервере (INTERNALDATE)
                    internaldate_m = re.search(r'INTERNALDATE\s+"([^"]+)"', meta_line, re.IGNORECASE)
                    parsed_internaldate = None
                    if internaldate_m:
                        try:
                            parsed_internaldate = parsedate_to_datetime(internaldate_m.group(1))
                        except Exception:
                            pass

                    msg_obj = email.message_from_bytes(raw_headers)
                    subject = decode_str(msg_obj.get("Subject")) or "(Без темы)"
                    from_raw = decode_str(msg_obj.get("From")) or ""
                    to_raw = decode_str(msg_obj.get("To")) or ""
                    date_raw = msg_obj.get("Date") or ""
                    content_type_raw = str(msg_obj.get("Content-Type") or "").lower()

                    has_attachments = (
                        "multipart/mixed" in content_type_raw
                        or "application/" in content_type_raw
                    )

                    from_name, from_email = parseaddr(from_raw)
                    if not from_name:
                        from_name = from_email or from_raw or "Без отправителя"

                    # Извлечение и парсинг списка адресатов (Кому / To)
                    recipients = getaddresses([to_raw])
                    to_display_list = []
                    for r_name, r_email in recipients:
                        r_name_clean = r_name.strip()
                        r_email_clean = r_email.strip()
                        if r_name_clean:
                            to_display_list.append(r_name_clean)
                        elif r_email_clean:
                            to_display_list.append(r_email_clean)

                    if to_display_list:
                        to_display = ", ".join(to_display_list)
                    elif to_raw.strip():
                        to_display = to_raw.strip()
                    else:
                        to_display = "Без получателя"

                    to_name, to_email = parseaddr(to_raw)
                    if not to_name:
                        to_name = to_email or to_display

                    parsed_date = None
                    if date_raw:
                        try:
                            parsed_date = parsedate_to_datetime(date_raw)
                        except Exception:
                            pass
                    if not parsed_date:
                        parsed_date = parsed_internaldate

                    messages_by_uid[item_uid] = {
                        "uid": item_uid,
                        "subject": subject,
                        "from_name": from_name,
                        "from_email": from_email,
                        "to_name": to_name,
                        "to_email": to_email,
                        "to_raw": to_raw,
                        "to_display": to_display,
                        "date": parsed_date,
                        "date_raw": date_raw or (parsed_date.strftime("%d.%m.%Y %H:%M") if parsed_date else ""),
                        "is_seen": is_seen,
                        "is_flagged": is_flagged,
                        "has_attachments": has_attachments,
                        "size_bytes": size_bytes,
                        "size_human": _format_file_size(size_bytes),
                    }
        except Exception as e:
            logger.error(f"[IMAP] Ошибка пакетного чтения заголовков: {e}")

        # Формируем итоговый список в точном порядке UIDs страницы
        messages = [messages_by_uid[u] for u in uids_ints if u in messages_by_uid]

        # In-Memory сверхбыстрая сортировка для кастомных полей (отправитель/получатель, тема, размер)
        is_sent_or_drafts = any(s in folder_name.lower() for s in ("sent", "отправленн", "draft", "черновик"))
        if sort_by == "from":
            if is_sent_or_drafts:
                messages.sort(key=lambda m: (m.get("to_display") or m.get("to_name") or "").lower(), reverse=(sort_dir == "desc"))
            else:
                messages.sort(key=lambda m: (m.get("from_name") or "").lower(), reverse=(sort_dir == "desc"))
        elif sort_by == "to":
            messages.sort(key=lambda m: (m.get("to_display") or m.get("to_name") or "").lower(), reverse=(sort_dir == "desc"))
        elif sort_by == "subject":
            messages.sort(key=lambda m: (m["subject"] or "").lower(), reverse=(sort_dir == "desc"))
        elif sort_by == "size":
            messages.sort(key=lambda m: m["size_bytes"], reverse=(sort_dir == "desc"))

        # Фильтр по наличию вложений, если указан filter=attachments
        if filter_by == "attachments":
            messages = [m for m in messages if m["has_attachments"]]

        # Сохраняем результат в кэш
        if email_clean:
            cache.set(cache_key, (messages, total_messages), timeout=180)

        return messages, total_messages

    def get_message_detail(self, folder_name: str, uid: int) -> Optional[Dict[str, Any]]:
        """Загружает полное содержимое письма со всеми частями и вложениями по точному UID.

        Args:
            folder_name (str): Папка письма.
            uid (int): Идентификатор сообщения (UID).

        Returns:
            dict, optional: Словарь с подробными данными письма.
        """
        if not self.client:
            return None

        # Открываем папку (сначала пробуем readonly=False, при отказе — readonly=True)
        status, _ = self.client.select(f'"{folder_name}"', readonly=False)
        if status != "OK":
            status, _ = self.client.select(f'"{folder_name}"', readonly=True)
            if status != "OK":
                logger.error(f"[IMAP] Не удалось выбрать папку {folder_name}: {status}")
                return None

        # Запрашиваем полное тело письма по UID с fallback
        fetch_queries = ["(RFC822)", "(BODY.PEEK[])", "(BODY[])"]
        data = None
        for q in fetch_queries:
            status, res_data = self.client.uid("fetch", str(uid), q)
            if status == "OK" and res_data and res_data != [None]:
                if any(isinstance(x, tuple) and len(x) >= 2 for x in res_data):
                    data = res_data
                    break

        if not data:
            logger.error(f"[IMAP] Ошибка fetch сообщения UID {uid} в {folder_name}")
            return None

        raw_email = None
        for response_part in data:
            if isinstance(response_part, tuple) and len(response_part) > 1:
                raw_email = response_part[1]
                break

        if not raw_email:
            logger.error(f"[IMAP] raw_email пустой для UID {uid} в {folder_name}")
            return None

        # Автоматически помечаем как прочитанное по UID и сбрасываем кэш
        try:
            self.client.uid("store", str(uid), "+FLAGS", "(\\Seen)")
            if self.email_addr:
                invalidate_mailbox_cache(self.email_addr)
        except Exception as e:
            logger.debug(f"[IMAP] Не удалось установить \\Seen для UID {uid}: {e}")

        msg = email.message_from_bytes(raw_email)
        subject = decode_str(msg.get("Subject")) or "(Без темы)"
        from_raw = decode_str(msg.get("From")) or ""
        to_raw = decode_str(msg.get("To")) or ""
        cc_raw = decode_str(msg.get("Cc")) or ""
        bcc_raw = decode_str(msg.get("Bcc")) or ""
        date_raw = msg.get("Date") or ""

        from_name, from_email = parseaddr(from_raw)
        if not from_name:
            from_name = from_email or from_raw or "Без отправителя"

        parsed_date = None
        if date_raw:
            try:
                parsed_date = parsedate_to_datetime(date_raw)
            except Exception:
                pass

        body_html = ""
        body_text = ""
        attachments = []
        raw_parts = []

        if msg.is_multipart():
            for part_idx, part in enumerate(msg.walk()):
                if part.is_multipart():
                    continue

                content_type = part.get_content_type().lower()
                content_disposition = str(part.get("Content-Disposition") or "").lower()
                content_id = str(part.get("Content-ID") or "").strip().strip("<>")
                content_location = str(part.get("Content-Location") or "").strip()
                filename = part.get_filename()

                if filename:
                    filename = decode_str(filename)

                payload = part.get_payload(decode=True)

                if content_type == "text/html" and not body_html and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or "utf-8"
                    body_html = payload.decode(charset, errors="replace") if payload else ""
                elif content_type == "text/plain" and not body_text and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace") if payload else ""
                else:
                    if payload:
                        raw_parts.append({
                            "part_index": part_idx,
                            "filename": filename,
                            "content_type": content_type,
                            "content_disposition": content_disposition,
                            "content_id": content_id,
                            "content_location": content_location,
                            "payload": payload,
                        })
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            content_type = msg.get_content_type().lower()
            if content_type == "text/html":
                body_html = payload.decode(charset, errors="replace") if payload else ""
            elif content_type == "text/plain":
                body_text = payload.decode(charset, errors="replace") if payload else ""
            elif payload:
                filename = msg.get_filename()
                filename = decode_str(filename) if filename else ""
                raw_parts.append({
                    "part_index": 0,
                    "filename": filename,
                    "content_type": content_type,
                    "content_disposition": str(msg.get("Content-Disposition") or "").lower(),
                    "content_id": str(msg.get("Content-ID") or "").strip().strip("<>"),
                    "content_location": str(msg.get("Content-Location") or "").strip(),
                    "payload": payload,
                })

        # Встраивание inline (CID) изображений в HTML-разметку подписи/тела
        inline_parts_used = set()
        if body_html and raw_parts:
            for item in raw_parts:
                p_type = item["content_type"]
                p_data = item["payload"]
                p_cid = item["content_id"]
                p_loc = item["content_location"]
                p_fname = item["filename"]

                if p_data and p_type.startswith("image/"):
                    b64_encoded = base64.b64encode(p_data).decode("ascii")
                    data_uri = f"data:{p_type};base64,{b64_encoded}"

                    replaced = False
                    # 1. Поиск по Content-ID (cid:...)
                    if p_cid:
                        pattern = re.compile(rf'cid:<?{re.escape(p_cid)}>?', re.IGNORECASE)
                        if pattern.search(body_html):
                            body_html = pattern.sub(data_uri, body_html)
                            inline_parts_used.add(item["part_index"])
                            replaced = True

                    # 2. Поиск по имени файла в src="cid:..." или src="..."
                    if not replaced and p_fname:
                        pattern_fname = re.compile(rf'cid:<?{re.escape(p_fname)}>?', re.IGNORECASE)
                        if pattern_fname.search(body_html):
                            body_html = pattern_fname.sub(data_uri, body_html)
                            inline_parts_used.add(item["part_index"])
                            replaced = True

                    # 3. Поиск по Content-Location
                    if not replaced and p_loc:
                        if p_loc in body_html:
                            body_html = body_html.replace(p_loc, data_uri)
                            inline_parts_used.add(item["part_index"])
                            replaced = True

        # Формирование списка реальных файлов-вложений (исключая встроенные картинки подписи)
        for item in raw_parts:
            part_idx = item["part_index"]
            c_disp = item["content_disposition"]
            c_type = item["content_type"]
            fname = item["filename"]
            payload = item["payload"]
            size_bytes = len(payload) if payload else 0

            # Если часть уже встроена в HTML как inline/CID — не показываем в блоке файлов
            if part_idx in inline_parts_used:
                continue

            # Если это декоративное inline-изображение без имени файла — не считаем вложением
            if "inline" in c_disp and not fname and c_type.startswith("image/"):
                continue

            if not fname:
                ext = c_type.split("/")[-1] if "/" in c_type else "dat"
                fname = f"attachment_{part_idx}.{ext}"

            is_img = c_type.startswith("image/") or fname.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
            )

            att_dict = {
                "part_index": part_idx,
                "filename": fname,
                "content_type": c_type,
                "size": size_bytes,
                "size_human": _format_file_size(size_bytes),
                "is_image": is_img,
            }
            try:
                from mailbox_app.services.attachment_security import enrich_attachment_dict
                enrich_attachment_dict(att_dict)
            except Exception as _sec_err:
                logger.warning(f"[Mailbox] Ошибка обогащения метаданных вложения: {_sec_err}")

            attachments.append(att_dict)

        # Если текста нет, но есть реальные вложения — выводим информационную плашку
        if not body_html and not body_text and attachments:
            body_html = "<div class='text-muted fst-italic py-2'><i class='bx bx-paperclip me-1'></i> Письмо без текста сообщения (содержит прикрепленные файлы)</div>"

        return {
            "uid": uid,
            "folder": folder_name,
            "subject": subject,
            "from_name": from_name,
            "from_email": from_email,
            "from_raw": from_raw,
            "to_raw": to_raw,
            "cc_raw": cc_raw,
            "bcc_raw": bcc_raw,
            "date": parsed_date,
            "date_raw": date_raw,
            "body_html": body_html,
            "body_text": body_text,
            "attachments": attachments,
            "message_id": msg.get("Message-ID", ""),
        }

    def download_attachment(
        self, folder_name: str, uid: int, part_index: int
    ) -> Optional[Tuple[str, str, bytes]]:
        """Извлекает конкретное бинарное вложение из письма по UID.

        Args:
            folder_name (str): Папка письма.
            uid (int): Идентификатор сообщения.
            part_index (int): Порядковый индекс части письма.

        Returns:
            tuple[str, str, bytes], optional: (filename, content_type, payload_bytes).
        """
        if not self.client:
            return None

        status, _ = self.client.select(f'"{folder_name}"', readonly=True)
        if status != "OK":
            return None

        fetch_queries = ["(RFC822)", "(BODY.PEEK[])", "(BODY[])"]
        data = None
        for q in fetch_queries:
            status, res_data = self.client.uid("fetch", str(uid), q)
            if status == "OK" and res_data and res_data != [None]:
                if any(isinstance(x, tuple) and len(x) >= 2 for x in res_data):
                    data = res_data
                    break

        if not data:
            return None

        raw_email = None
        for response_part in data:
            if isinstance(response_part, tuple) and len(response_part) > 1:
                raw_email = response_part[1]
                break

        if not raw_email:
            return None

        msg = email.message_from_bytes(raw_email)

        for current_idx, part in enumerate(msg.walk()):
            if current_idx == part_index:
                content_type = part.get_content_type()
                filename = decode_str(part.get_filename())
                if not filename:
                    ext = content_type.split("/")[-1] if "/" in content_type else "dat"
                    filename = f"attachment_{part_index}.{ext}"

                payload = part.get_payload(decode=True)
                return filename, content_type, payload

        # Если сообщение не multipart и индекс 0
        if not msg.is_multipart() and part_index == 0:
            content_type = msg.get_content_type()
            filename = decode_str(msg.get_filename())
            if not filename:
                ext = content_type.split("/")[-1] if "/" in content_type else "dat"
                filename = f"attachment_0.{ext}"
            payload = msg.get_payload(decode=True)
            return filename, content_type, payload

        return None

    def toggle_flag(self, folder_name: str, uid: int, flag_name: str = "\\Flagged") -> bool:
        """Переключает флаг письма (например, важность) по UID.

        Args:
            folder_name (str): Папка письма.
            uid (int): Идентификатор сообщения.
            flag_name (str): Имя флага IMAP.

        Returns:
            bool: True в случае успеха.
        """
        if not self.client:
            return False
        self.client.select(f'"{folder_name}"', readonly=False)
        status, data = self.client.uid("fetch", str(uid), "(FLAGS)")
        if status != "OK" or not data:
            return False

        meta_line = data[0].decode("latin-1") if isinstance(data[0], bytes) else str(data[0])
        action = "-FLAGS" if flag_name in meta_line else "+FLAGS"
        self.client.uid("store", str(uid), action, f"({flag_name})")
        invalidate_mailbox_cache(self.email_addr)
        return True

    def mark_seen(self, folder_name: str, uid: int, is_seen: bool = True) -> bool:
        """Устанавливает статус прочитанности письма по UID.

        Args:
            folder_name (str): Папка.
            uid (int): Идентификатор.
            is_seen (bool): True - прочитано, False - непрочитано.

        Returns:
            bool: Результат операции.
        """
        if not self.client:
            return False
        self.client.select(f'"{folder_name}"', readonly=False)
        action = "+FLAGS" if is_seen else "-FLAGS"
        self.client.uid("store", str(uid), action, "(\\Seen)")
        invalidate_mailbox_cache(self.email_addr)
        return True

    def delete_message(self, folder_name: str, uid: int) -> bool:
        """Перемещает письмо в корзину или удаляет навсегда по UID.

        Args:
            folder_name (str): Исходная папка.
            uid (int): Идентификатор сообщения.

        Returns:
            bool: Результат операции.
        """
        if not self.client:
            return False
        self.client.select(f'"{folder_name}"', readonly=False)

        # Если уже в Корзине — удаляем навсегда
        if "trash" in folder_name.lower() or "корзин" in folder_name.lower() or "deleted" in folder_name.lower():
            self.client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
            self.client.expunge()
            invalidate_mailbox_cache(self.email_addr)
            return True

        # Иначе пробуем переместить в корзину
        folders = self.get_folders()
        trash_folder = next((f["raw_name"] for f in folders if f["type"] == "trash"), None)

        if trash_folder:
            self.client.uid("copy", str(uid), f'"{trash_folder}"')
            self.client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
            self.client.expunge()
        else:
            self.client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
            self.client.expunge()

        invalidate_mailbox_cache(self.email_addr)
        return True

    def unmark_spam(self, folder_name: str, uid: int) -> Tuple[bool, Optional[Tuple[str, str]]]:
        """Снимает спам-метки ($Junk), выставляет флаги обучения ($NotJunk) и перемещает письмо в INBOX.

        Args:
            folder_name (str): Папка со спамом (Junk E-mail / Спам).
            uid (int): Идентификатор сообщения (UID).

        Returns:
            tuple[bool, Optional[tuple[str, str]]]: (успех, (from_name, from_email) для авто-вайтлиста).
        """
        if not self.client:
            return False, None

        status, _ = self.client.select(f'"{folder_name}"', readonly=False)
        if status != "OK":
            return False, None

        sender_info = None
        try:
            # Считываем From для сохранения в белый список
            fetch_st, fetch_dt = self.client.uid(
                "fetch", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM)])"
            )
            if fetch_st == "OK" and fetch_dt and fetch_dt[0] and isinstance(fetch_dt[0], tuple):
                from_hdr = email.message_from_bytes(fetch_dt[0][1]).get("From", "")
                f_name, f_email = parseaddr(decode_str(from_hdr))
                if f_email:
                    sender_info = (f_name or f_email, f_email)
        except Exception as e:
            logger.debug(f"[IMAP] Ошибка чтения отправителя при unmark_spam: {e}")

        # 1. Обучение спам-фильтра сервера (Kerio Connect / SpamAssassin / Dovecot):
        # Удаляем метки Junk и добавляем системные ключевые слова $NotJunk / NonJunk
        try:
            self.client.uid("store", str(uid), "-FLAGS", "($Junk Junk)")
        except Exception:
            pass
        try:
            self.client.uid("store", str(uid), "+FLAGS", "($NotJunk NotJunk NonJunk)")
        except Exception:
            pass

        # 2. Находим целевую папку «Входящие» (INBOX)
        folders = self.get_folders()
        inbox_folder = next((f["raw_name"] for f in folders if f["type"] == "inbox"), "INBOX")

        # 3. Перемещаем сообщение в INBOX
        try:
            copy_st, _ = self.client.uid("copy", str(uid), f'"{inbox_folder}"')
            if copy_st == "OK":
                self.client.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
                self.client.expunge()
                invalidate_mailbox_cache(self.email_addr)
                return True, sender_info
        except Exception as e:
            logger.error(f"[IMAP] Ошибка переноса письма UID {uid} из спама в {inbox_folder}: {e}")

        return False, None

    def save_draft(
        self,
        to_recipients: str,
        subject: str,
        body_html: str,
        cc_recipients: str = "",
        bcc_recipients: str = "",
        old_draft_uid: Optional[int] = None,
    ) -> Optional[int]:
        """Сохраняет черновик письма в папку 'Черновики' на сервере IMAP.

        Args:
            to_recipients (str): Адресаты письма.
            subject (str): Тема письма.
            body_html (str): HTML-разметка тела письма.
            cc_recipients (str, optional): Адресаты в копии.
            bcc_recipients (str, optional): Адресаты в скрытой копии.
            old_draft_uid (int, optional): UID предыдущего черновика для замены.

        Returns:
            int, optional: UID сохраненного черновика или None при ошибке.
        """
        if not self.client:
            return None

        folders = self.get_folders()
        drafts_folder = next(
            (
                f["raw_name"]
                for f in folders
                if f.get("type") == "drafts" or f.get("root_type") == "drafts"
            ),
            None,
        )
        if not drafts_folder:
            drafts_folder = "Drafts"

        # Если передан старый draft_uid — удаляем старую версию черновика
        if old_draft_uid:
            try:
                self.client.select(f'"{drafts_folder}"', readonly=False)
                self.client.uid("store", str(old_draft_uid), "+FLAGS", "(\\Deleted)")
                self.client.expunge()
            except Exception as err:
                logger.debug(f"[IMAP] Не удалось удалить старый черновик UID {old_draft_uid}: {err}")

        from mailbox_app.services.smtp_service import format_recipient_addresses

        # Формируем MIME сообщение черновика
        msg = MIMEMultipart("alternative")
        msg["From"] = self.email_addr
        to_hdr, _ = format_recipient_addresses(to_recipients)
        if to_hdr:
            msg["To"] = to_hdr
        cc_hdr, _ = format_recipient_addresses(cc_recipients)
        if cc_hdr:
            msg["Cc"] = cc_hdr
        bcc_hdr, _ = format_recipient_addresses(bcc_recipients)
        if bcc_hdr:
            msg["Bcc"] = bcc_hdr
        msg["Subject"] = Header(subject or "(Без темы)", "utf-8")
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        msg["X-Unsent"] = "1"

        plain_text = re.sub(r"<[^>]+>", "", body_html or "")
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html or "", "html", "utf-8"))

        msg_bytes = msg.as_bytes()

        try:
            status, resp = self.client.append(
                f'"{drafts_folder}"',
                "(\\Draft \\Seen)",
                imaplib.Time2Internaldate(time.time()),
                msg_bytes,
            )
            if status != "OK":
                logger.error(f"[IMAP] Ошибка сохранения черновика в {drafts_folder}: {resp}")
                return None

            new_uid = None
            # Пробуем извлечь APPENDUID из ответа сервера (RFC 4315)
            if resp and isinstance(resp, list):
                resp_str = " ".join(str(r) for r in resp)
                match = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp_str)
                if match:
                    new_uid = int(match.group(1))

            if not new_uid:
                # Если APPENDUID не вернулся, находим последний UID в папке
                self.client.select(f'"{drafts_folder}"', readonly=True)
                s_stat, s_data = self.client.uid("SEARCH", None, "ALL")
                if s_stat == "OK" and s_data and s_data[0]:
                    all_uids = s_data[0].split()
                    if all_uids:
                        new_uid = int(all_uids[-1])

            invalidate_mailbox_cache(self.email_addr)
            return new_uid

        except Exception as e:
            logger.error(f"[IMAP] Исключение при сохранении черновика: {e}", exc_info=True)
            return None

    def delete_draft(self, draft_uid: int) -> bool:
        """Удаляет черновик из папки черновиков по UID.

        Args:
            draft_uid (int): Идентификатор черновика.

        Returns:
            bool: True в случае успешного удаления.
        """
        if not self.client:
            return False

        folders = self.get_folders()
        drafts_folder = next(
            (
                f["raw_name"]
                for f in folders
                if f.get("type") == "drafts" or f.get("root_type") == "drafts"
            ),
            "Drafts",
        )
        try:
            self.client.select(f'"{drafts_folder}"', readonly=False)
            self.client.uid("store", str(draft_uid), "+FLAGS", "(\\Deleted)")
            self.client.expunge()
            invalidate_mailbox_cache(self.email_addr)
            return True
        except Exception as e:
            logger.error(f"[IMAP] Ошибка удаления черновика UID {draft_uid}: {e}")
            return False

    def move_messages(self, folder_name: str, uids: List[int], target_folder: str) -> bool:
        """Перемещает список писем по UID в целевую папку.

        Поддерживает RFC 6851 (IMAP MOVE) с отказоустойчивым fallback на COPY + STORE + EXPUNGE.

        Args:
            folder_name (str): Исходная папка.
            uids (list[int]): Список идентификаторов писем.
            target_folder (str): Имя целевой папки назначения.

        Returns:
            bool: True в случае успешного перемещения.
        """
        if not self.client or not uids:
            return False

        status, _ = self.client.select(f'"{folder_name}"', readonly=False)
        if status != "OK":
            return False

        uid_set = ",".join(str(u) for u in uids)

        # 1. Пробуем нативную команду MOVE (RFC 6851)
        try:
            mv_status, _ = self.client.uid("MOVE", uid_set, f'"{target_folder}"')
            if mv_status == "OK":
                invalidate_mailbox_cache(self.email_addr)
                return True
        except Exception:
            pass

        # 2. Fallback: COPY -> STORE \Deleted -> EXPUNGE
        try:
            cp_status, _ = self.client.uid("COPY", uid_set, f'"{target_folder}"')
            if cp_status == "OK":
                self.client.uid("store", uid_set, "+FLAGS", "(\\Deleted)")
                self.client.expunge()
                invalidate_mailbox_cache(self.email_addr)
                return True
        except Exception as e:
            logger.error(f"[IMAP] Ошибка перемещения писем {uid_set} в {target_folder}: {e}")

        return False

    def batch_action(
        self, folder_name: str, uids: List[int], action: str, target_folder: str = ""
    ) -> bool:
        """Выполняет массовое групповое действие над списком писем.

        Args:
            folder_name (str): Исходная папка.
            uids (list[int]): Список UID писем.
            action (str): Действие ('mark_seen', 'mark_unseen', 'toggle_flag', 'delete', 'move').
            target_folder (str, optional): Целевая папка для действия 'move'.

        Returns:
            bool: True в случае успешного выполнения.
        """
        if not self.client or not uids:
            return False

        if action == "move":
            return self.move_messages(folder_name, uids, target_folder)

        status, _ = self.client.select(f'"{folder_name}"', readonly=False)
        if status != "OK":
            return False

        uid_set = ",".join(str(u) for u in uids)

        try:
            if action == "mark_seen":
                self.client.uid("store", uid_set, "+FLAGS", "(\\Seen)")
            elif action == "mark_unseen":
                self.client.uid("store", uid_set, "-FLAGS", "(\\Seen)")
            elif action == "toggle_flag":
                self.client.uid("store", uid_set, "+FLAGS", "(\\Flagged)")
            elif action == "delete":
                if (
                    "trash" in folder_name.lower()
                    or "корзин" in folder_name.lower()
                    or "deleted" in folder_name.lower()
                ):
                    self.client.uid("store", uid_set, "+FLAGS", "(\\Deleted)")
                    self.client.expunge()
                else:
                    folders = self.get_folders()
                    trash_folder = next(
                        (f["raw_name"] for f in folders if f["type"] == "trash"),
                        None,
                    )
                    if trash_folder:
                        return self.move_messages(folder_name, uids, trash_folder)
                    else:
                        self.client.uid("store", uid_set, "+FLAGS", "(\\Deleted)")
                        self.client.expunge()

            invalidate_mailbox_cache(self.email_addr)
            return True
        except Exception as e:
            logger.error(f"[IMAP] Ошибка batch_action '{action}' для {uid_set}: {e}")
            return False

    def mark_all_read(self, folder_name: str) -> int:
        """Помечает все непрочитанные сообщения в указанной папке как прочитанные.

        Args:
            folder_name (str): Название папки IMAP.

        Returns:
            int: Количество обновленных сообщений.
        """
        if not self.client:
            return 0

        status, _ = self.client.select(f'"{folder_name}"', readonly=False)
        if status != "OK":
            return 0

        try:
            status, search_data = self.client.uid("search", None, "UNSEEN")
            if status != "OK" or not search_data or not search_data[0]:
                return 0

            raw_uids = [u for u in search_data[0].split() if u and u != b"0"]
            if not raw_uids:
                return 0

            uid_set = ",".join(u.decode("ascii") if isinstance(u, bytes) else str(u) for u in raw_uids)
            self.client.uid("store", uid_set, "+FLAGS", "(\\Seen)")
            invalidate_mailbox_cache(self.email_addr)
            return len(raw_uids)
        except Exception as e:
            logger.error(f"[IMAP] Ошибка отметки всех писем прочитанными в папке {folder_name}: {e}")
            return 0



def _format_file_size(size_in_bytes: int) -> str:
    """Форматирует размер файла в удобочитаемый вид (КБ, МБ).

    Args:
        size_in_bytes (int): Размер в байтах.

    Returns:
        str: Человекочитаемая строка размера.
    """
    if size_in_bytes < 1024:
        return f"{size_in_bytes} Б"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} КБ"
    else:
        return f"{size_in_bytes / (1024 * 1024):.1f} МБ"
