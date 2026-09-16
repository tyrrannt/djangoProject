"""Вспомогательные утилиты транслитерации и генерации логинов корпоративной почты BARKOL."""

import logging
import re
import secrets
import string
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def generate_random_password(
    length: int = 16,
    use_lowercase: bool = True,
    use_uppercase: bool = True,
    use_digits: bool = True,
    use_special: bool = True,
    special_chars: str = "!@#$%&*-_=+",
) -> str:
    """Генерирует надежный случайный пароль для почтовых учетных записей с настраиваемым алфавитом.

    Позволяет гибко управлять длиной пароля и используемыми группами символов
    (строчные, прописные, цифры, спецсимволы). Гарантирует наличие как минимум одного
    символа из каждого активного класса.

    Args:
        length (int): Длина пароля (от 6 до 128 символов, по умолчанию 16).
        use_lowercase (bool): Включать ли строчные латинские буквы (a-z). По умолчанию True.
        use_uppercase (bool): Включать ли прописные латинские буквы (A-Z). По умолчанию True.
        use_digits (bool): Включать ли цифры (0-9). По умолчанию True.
        use_special (bool): Включать ли специальные символы. По умолчанию True.
        special_chars (str): Набор допустимых спецсимволов. По умолчанию '!@#$%&*-_=+'.

    Returns:
        str: Сгенерированный криптостойкий пароль.

    Raises:
        ValueError: Если не выбрана ни одна группа символов или длина меньше минимальной.

    Example:
        >>> pwd = generate_random_password(length=12, use_special=False)
        >>> len(pwd) == 12
        True
    """
    clean_length = max(6, min(128, int(length or 16)))
    pools: List[str] = []

    if use_lowercase:
        pools.append(string.ascii_lowercase)
    if use_uppercase:
        pools.append(string.ascii_uppercase)
    if use_digits:
        pools.append(string.digits)
    if use_special:
        clean_specials = "".join(ch for ch in str(special_chars or "!@#$%&*-_=+") if not ch.isspace())
        if clean_specials:
            pools.append(clean_specials)

    if not pools:
        # Fallback по умолчанию: латиница и цифры
        pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits]

    combined_alphabet = "".join(pools)

    # Гарантируем присутствие каждого выбранного класса символов
    while True:
        candidate = "".join(secrets.choice(combined_alphabet) for _ in range(clean_length))
        if all(any(c in pool for c in candidate) for pool in pools):
            return candidate



# Таблица транслитерации русского алфавита в латиницу по стандарту BARKOL / ГОСТ
TRANSLIT_TABLE: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate_ru_to_en(text: str) -> str:
    """Выполняет транслитерацию русскоязычного текста на латиницу по корпоративному стандарту.

    Приводит все символы к нижнему регистру, заменяет кириллические буквы
    в соответствии с таблицей TRANSLIT_TABLE, сохраняет латинские буквы,
    цифры и дефисы, удаляя спецсимволы и пробелы.

    Args:
        text (str): Исходная русскоязычная строка (ФИО, имя или фамилия).

    Returns:
        str: Транслитерированная строка в нижнем регистре.

    Example:
        >>> transliterate_ru_to_en("Абрамов")
        'abramov'
        >>> transliterate_ru_to_en("Чупрына")
        'chupryna'
        >>> transliterate_ru_to_en("Мамин-Сибиряк")
        'mamin-sibiryak'
    """
    if not text:
        return ""

    clean_text = text.strip().lower()
    result_chars: List[str] = []

    for char in clean_text:
        if char in TRANSLIT_TABLE:
            result_chars.append(TRANSLIT_TABLE[char])
        elif re.match(r"[a-z0-9\-]", char):
            result_chars.append(char)
        # пробелы и прочие спецсимволы опускаются или заменяются при парсинге ФИО

    return "".join(result_chars)


def parse_fio_components(user_or_fio: Any) -> Tuple[str, str, str]:
    """Извлекает компоненты (Имя, Фамилия, Отчество) из объекта пользователя или строки ФИО.

    Args:
        user_or_fio (Any): Экземпляр DataBaseUser или строка с ФИО (например, "Иванов Иван Иванович").

    Returns:
        Tuple[str, str, str]: Кортеж (first_name, last_name, middle_name) в оригинальном регистре.
    """
    first_name = ""
    last_name = ""
    middle_name = ""

    # Если передан объект модели пользователя Django (DataBaseUser)
    if hasattr(user_or_fio, "last_name") or hasattr(user_or_fio, "first_name"):
        last_name = getattr(user_or_fio, "last_name", "") or ""
        first_name = getattr(user_or_fio, "first_name", "") or ""
        middle_name = getattr(user_or_fio, "surname", "") or ""

        # Если поля first_name/last_name пусты, пытаемся распарсить поле title
        if (not last_name or not first_name) and getattr(user_or_fio, "title", None):
            title_parts = [p.strip() for p in str(user_or_fio.title).split() if p.strip()]
            if len(title_parts) >= 1 and not last_name:
                last_name = title_parts[0]
            if len(title_parts) >= 2 and not first_name:
                first_name = title_parts[1]
            if len(title_parts) >= 3 and not middle_name:
                middle_name = title_parts[2]

    elif isinstance(user_or_fio, str):
        parts = [p.strip() for p in user_or_fio.split() if p.strip()]
        if len(parts) >= 1:
            last_name = parts[0]
        if len(parts) >= 2:
            first_name = parts[1]
        if len(parts) >= 3:
            middle_name = parts[2]

    return first_name, last_name, middle_name


def generate_corporate_mailbox_login(
    first_name: str,
    last_name: str,
    middle_name: str = "",
    existing_logins: Optional[Set[str]] = None,
) -> str:
    """Генерирует уникальный корпоративный логин почтового ящика BARKOL по регламенту разрешения коллизий.

    Регламент формирования логина в компании BARKOL:
    - **Уровень 1 (Стандарт)**: `<первая_буква_имени>.<фамилия>` (например: `a.abramov`).
    - **Уровень 2 (Коллизия имени, инициал отчества)**: если базовый логин занят, используется
      `<первая_буква_имени><первая_буква_отчества>.<фамилия>` (например: `ab.abramov`).
    - **Уровень 3 (Коллизия отчества, полное имя)**: если отчество отсутствует или вариант занят,
      используется `<полное_имя>.<фамилия>` (например: `aleksey.abramov`).
    - **Уровень 4 (Полные тезки, числовой суффикс)**: если все предыдущие варианты заняты,
      добавляется числовой инкрементный индекс: `<первая_буква_имени>.<фамилия><N>` (например: `a.abramov2`, `a.abramov3`).

    Args:
        first_name (str): Имя сотрудника (рус. или лат.).
        last_name (str): Фамилия сотрудника (рус. или лат.).
        middle_name (str): Отчество сотрудника (при наличии).
        existing_logins (Optional[Set[str]]): Множество уже занятых логинов на сервере.

    Returns:
        str: Сгенерированный уникальный логин в нижнем регистре.
    """
    clean_last = transliterate_ru_to_en(last_name)
    clean_first = transliterate_ru_to_en(first_name)
    clean_middle = transliterate_ru_to_en(middle_name)

    # Если фамилия не указана, используем имя или безопасный fallback
    if not clean_last and clean_first:
        clean_last = clean_first
        clean_first = ""

    if not clean_last:
        return "user"

    first_init = clean_first[0] if clean_first else ""
    middle_init = clean_middle[0] if clean_middle else ""

    occupied = set(l.lower().strip() for l in existing_logins) if existing_logins else set()

    # Вариант 1: <инициал_имени>.<фамилия> (a.abramov)
    candidate_1 = f"{first_init}.{clean_last}" if first_init else clean_last
    if candidate_1 not in occupied:
        return candidate_1

    # Вариант 2: <инициал_имени><инициал_отчества>.<фамилия> (ab.abramov)
    if first_init and middle_init:
        candidate_2 = f"{first_init}{middle_init}.{clean_last}"
        if candidate_2 not in occupied:
            return candidate_2

    # Вариант 3: <полное_имя>.<фамилия> (aleksey.abramov)
    if clean_first and len(clean_first) > 1:
        candidate_3 = f"{clean_first}.{clean_last}"
        if candidate_3 not in occupied:
            return candidate_3

    # Вариант 4: <инициал_имени>.<фамилия><N> (a.abramov2, a.abramov3, ...)
    base_prefix = f"{first_init}.{clean_last}" if first_init else clean_last
    counter = 2
    while True:
        candidate_n = f"{base_prefix}{counter}"
        if candidate_n not in occupied:
            return candidate_n
        counter += 1


def get_all_existing_logins_set() -> Set[str]:
    """Собирает полный набор уже занятых логинов из БД Django (MailAccount, User) и Kerio Connect.

    Returns:
        Set[str]: Множество занятых логинов в нижнем регистре.
    """
    logins: Set[str] = set()

    try:
        from django.contrib.auth import get_user_model
        from mailbox_app.models import MailAccount

        User = get_user_model()
        for u in User.objects.values_list("username", flat=True):
            if u:
                logins.add(u.strip().lower())

        for email in MailAccount.objects.values_list("email", flat=True):
            if email:
                logins.add(email.split("@")[0].strip().lower())
    except Exception:
        pass

    return logins


def get_django_setting(name: str, default: Any = None) -> Any:
    """Безопасно извлекает значение настройки из django.conf.settings.

    Гарантирует отсутствие исключений (ImproperlyConfigured, AttributeError,
    ImportError), если settings не сконфигурирован или запуск производится
    вне контекста Django приложения (в изолированных unit-тестах).

    Args:
        name (str): Имя параметра конфигурации Django (например, 'KERIO_API_URL').
        default (Any, optional): Значение по умолчанию. Defaults to None.

    Returns:
        Any: Значение настройки Django или default.

    Example:
        >>> get_django_setting("KERIO_DEFAULT_SMTP_RELAY_HOST", "smtp.barkol.ru")
        'smtp.barkol.ru'
    """
    try:
        from django.conf import settings
        if settings.configured:
            return getattr(settings, name, default)
    except Exception:
        pass
    return default


def find_portal_user_by_kerio_identity(
    login_name: str,
    domain_name: str = "barkol.ru",
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    user_id: Optional[int] = None,
    client: Optional[Any] = None,
) -> Optional[Any]:
    """Выполняет интеллектуальный многоуровневый поиск профиля сотрудника DataBaseUser на портале.

    Применяет многоуровневые стратегии сопоставления:
    1. По явному `user_id` (PK модели DataBaseUser).
    2. По прямому совпадению корпоративного `email` (full_email) в `DataBaseUser.email`.
    3. По точному совпадению `username` (логин, логин с заменой точек на подчеркивания или удалением точек).
    4. По связанной записи `MailAccount` (по email или `user__username`).
    5. По переданному ФИО `full_name` (фамилия + инициал имени / title).
    6. По данным из Kerio Connect API (если передан `client`, запрашивается fullName и contact).
    7. По регламенту корпоративного именования BARKOL (инициал имени + транслитерированная фамилия):
       извлекает транслитерированную фамилию (например 'adygezalov' из 'o.adygezalov') и инициал ('o'),
       сопоставляя с русскоязычными полями `last_name` ('Адыгезалов') и `first_name` ('Омар') активных пользователей портала.

    Args:
        login_name (str): Логин пользователя в Kerio Connect (например, 'o.adygezalov' или 'o.adygezalov@barkol.ru').
        domain_name (str, optional): Имя домена. Defaults to "barkol.ru".
        email (Optional[str], optional): Явный адрес email. Defaults to None.
        full_name (Optional[str], optional): ФИО сотрудника (если известно). Defaults to None.
        user_id (Optional[int], optional): Идентификатор пользователя Django (PK). Defaults to None.
        client (Optional[Any], optional): Экземпляр KerioConnectAdminClient для подгрузки данных пользователя. Defaults to None.

    Returns:
        Optional[Any]: Найденный объект модели DataBaseUser либо None.
    """
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        from mailbox_app.models import MailAccount
    except Exception:
        return None

    User = get_user_model()
    if not User:
        return None

    # 1. Поиск по явному user_id
    if user_id:
        try:
            u = User.objects.filter(pk=user_id).select_related("user_work_profile").first()
            if u:
                return u
        except Exception:
            pass

    clean_login = login_name.split("@")[0].strip().lower() if login_name else ""
    target_domain = domain_name.strip().lower() if domain_name else "barkol.ru"
    full_email = str(email).strip().lower() if email else (f"{clean_login}@{target_domain}" if clean_login else "")

    if not clean_login and not full_email:
        return None

    # 2. Поиск по прямому email и username
    q_filter = models.Q()
    if full_email:
        q_filter |= models.Q(email__iexact=full_email)
    if clean_login:
        q_filter |= models.Q(username__iexact=clean_login)
        if "." in clean_login:
            q_filter |= models.Q(username__iexact=clean_login.replace(".", "_"))
            q_filter |= models.Q(username__iexact=clean_login.replace(".", ""))

    portal_user = User.objects.filter(q_filter).select_related("user_work_profile").first()
    if portal_user:
        return portal_user

    # 3. Поиск через модель MailAccount
    if MailAccount:
        acc_q = models.Q()
        if full_email:
            acc_q |= models.Q(email__iexact=full_email)
        if clean_login:
            acc_q |= models.Q(user__username__iexact=clean_login)
        acc = MailAccount.objects.filter(acc_q).select_related("user", "user__user_work_profile").first()
        if acc and acc.user:
            return acc.user

    # 4. Попытка получить fullName из Kerio Connect API, если не передан
    effective_full_name = (full_name or "").strip()
    if not effective_full_name and client and clean_login:
        try:
            from mailbox_app.services.kerio.users import UserManager
            u_mgr = UserManager(client)
            k_user = u_mgr.get_user_by_login(clean_login)
            if k_user:
                effective_full_name = str(k_user.get("fullName") or "").strip()
                if not effective_full_name:
                    contact = k_user.get("contact", {})
                    if isinstance(contact, dict):
                        c_first = contact.get("firstName", "")
                        c_last = contact.get("lastName", "")
                        c_mid = contact.get("middleName", "")
                        effective_full_name = f"{c_last} {c_first} {c_mid}".strip()
        except Exception:
            pass

    # 5. Поиск по ФИО (first_name, last_name, title)
    if effective_full_name:
        f_name, l_name, m_name = parse_fio_components(effective_full_name)
        if l_name:
            candidates = list(
                User.objects.filter(
                    models.Q(last_name__iexact=l_name) | models.Q(title__icontains=l_name)
                ).select_related("user_work_profile")
            )
            if f_name:
                f_init = f_name[0].upper()
                f_matched = [
                    c for c in candidates
                    if (c.first_name and c.first_name.upper().startswith(f_init))
                    or (c.title and l_name in c.title and f_init in c.title)
                ]
                if f_matched:
                    active_m = [c for c in f_matched if c.is_active]
                    return active_m[0] if active_m else f_matched[0]
            if candidates:
                active_c = [c for c in candidates if c.is_active]
                return active_c[0] if active_c else candidates[0]

    # 6. Эвристический разбор логина по стандарту BARKOL (инициал имени + транслитерированная фамилия)
    if clean_login:
        login_base = re.sub(r"\d+$", "", clean_login)
        initials = ""
        translit_last = ""

        if "." in login_base:
            parts = [p.strip() for p in login_base.split(".") if p.strip()]
            if len(parts) >= 2:
                translit_last = parts[-1]
                initials = "".join(parts[:-1])
            elif len(parts) == 1:
                translit_last = parts[0]
        else:
            translit_last = login_base

        if translit_last:
            users_qs = list(User.objects.filter(is_active=True).select_related("user_work_profile"))
            matched_candidates: List[Any] = []

            for u in users_qs:
                u_last = getattr(u, "last_name", "") or ""
                u_first = getattr(u, "first_name", "") or ""
                u_title = getattr(u, "title", "") or ""
                u_uname = getattr(u, "username", "") or ""

                u_translit_last = transliterate_ru_to_en(u_last)
                u_translit_first = transliterate_ru_to_en(u_first)

                last_matches = False
                if u_translit_last and u_translit_last == translit_last:
                    last_matches = True
                elif u_uname.lower() == translit_last or u_uname.lower().startswith(translit_last):
                    last_matches = True
                elif translit_last in transliterate_ru_to_en(u_title):
                    last_matches = True

                if last_matches:
                    if initials and u_translit_first:
                        if u_translit_first.startswith(initials[0]):
                            matched_candidates.insert(0, u)
                        else:
                            matched_candidates.append(u)
                    else:
                        matched_candidates.append(u)

            if matched_candidates:
                return matched_candidates[0]

    return None


def collect_all_portal_smtp_passwords(default_domain: str = "barkol.ru") -> Dict[str, str]:
    """Формирует полную карту всех сохраненных внешних паролей (ISPManager / Доставка SMTP) из базы данных портала.

    Собирает пароли из трех источников:
    1. Профилей сотрудников DataBaseUserWorkProfile (work_application_password, с fallback на work_email_password);
    2. Корпоративных и ведомственных почтовых ящиков Mailbox (work_application_password, с fallback на get_smtp_password);
    3. Персональных почтовых аккаунтов MailAccount (get_password).

    Args:
        default_domain (str): Почтовый домен по умолчанию для логинов без символа '@'. По умолчанию 'barkol.ru'.

    Returns:
        Dict[str, str]: Словарь сопоставления {email: пароль} для всех обнаруженных ящиков.

    Example:
        >>> passwords = collect_all_portal_smtp_passwords()
        >>> isinstance(passwords, dict)
        True
    """
    passwords_map: Dict[str, str] = {}
    clean_default_domain = str(default_domain or "barkol.ru").strip().lower()

    # 1. Профили сотрудников DataBaseUserWorkProfile
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users_qs = User.objects.select_related("user_work_profile").all()
        for u in users_qs:
            email = str(getattr(u, "email", "") or "").strip().lower()
            username = str(getattr(u, "username", "") or "").strip().lower()
            if not email and username:
                email = f"{username}@{clean_default_domain}"
            if not email or "@" not in email:
                continue
            wp = getattr(u, "user_work_profile", None)
            if wp:
                ext_pwd = str(getattr(wp, "work_application_password", "") or "").strip()
                if not ext_pwd:
                    ext_pwd = str(getattr(wp, "work_email_password", "") or "").strip()
                if ext_pwd:
                    passwords_map[email] = ext_pwd
                    if username and f"{username}@{clean_default_domain}" not in passwords_map:
                        passwords_map[f"{username}@{clean_default_domain}"] = ext_pwd
    except Exception as u_err:
        logger.debug(f"[collect_all_portal_smtp_passwords] Ошибка сбора паролей пользователей: {u_err}")

    # 2. Корпоративные и ведомственные почтовые ящики Mailbox
    try:
        from mailbox_app.models import Mailbox
        for mb in Mailbox.objects.all():
            email = str(getattr(mb, "email", "") or "").strip().lower()
            if not email:
                continue
            mb_pwd = str(getattr(mb, "work_application_password", "") or "").strip()
            if not mb_pwd:
                try:
                    mb_pwd = str(mb.get_smtp_password() or "").strip()
                except Exception:
                    mb_pwd = ""
            if mb_pwd:
                passwords_map[email] = mb_pwd
    except Exception as mb_err:
        logger.debug(f"[collect_all_portal_smtp_passwords] Ошибка сбора паролей Mailbox: {mb_err}")

    # 3. Персональные ящики MailAccount
    try:
        from mailbox_app.models import MailAccount
        for acc in MailAccount.objects.all():
            email = str(getattr(acc, "email", "") or "").strip().lower()
            if not email:
                continue
            try:
                acc_pwd = str(acc.get_password() or "").strip()
            except Exception:
                acc_pwd = ""
            if acc_pwd and email not in passwords_map:
                passwords_map[email] = acc_pwd
    except Exception as acc_err:
        logger.debug(f"[collect_all_portal_smtp_passwords] Ошибка сбора паролей MailAccount: {acc_err}")

    return passwords_map
