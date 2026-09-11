"""Вспомогательные утилиты транслитерации и генерации логинов корпоративной почты BARKOL."""

import re
import secrets
import string
from typing import Any, List, Optional, Set, Tuple


def generate_random_password(length: int = 16) -> str:
    """Генерирует надежный случайный ASCII-пароль для почтовых учетных записей.

    Гарантирует наличие строчных и прописных латинских букв, цифр и безопасных спецсимволов.

    Args:
        length (int): Длина пароля (по умолчанию 16).

    Returns:
        str: Сгенерированный пароль.
    """
    specials = "!@#$%^&*()-_=+"
    alphabet = string.ascii_letters + string.digits + specials
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(max(8, length)))
        if (
            any(c.islower() for c in pwd)
            and any(c.isupper() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in specials for c in pwd)
        ):
            return pwd



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
