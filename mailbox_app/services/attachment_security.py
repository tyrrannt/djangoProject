"""Сервисный модуль классификации безопасности и форматирования почтовых вложений.

Обеспечивает категоризацию файлов по уровню риска информационной безопасности
(высокий, средний, низкий, нейтральный), выбор подходящего режима браузерного
предпросмотра и умное форматирование длинных имен файлов с гарантированным
сохранением расширения.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple


# Расширения с составными суффиксами (например, .tar.gz)
COMPOUND_EXTENSIONS: Tuple[str, ...] = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".backup.tar",
)

# Классификация уровней риска безопасности
HIGH_RISK_EXTENSIONS: frozenset[str] = frozenset([
    # Исполняемые файлы и инсталляторы
    "exe", "msi", "msp", "bat", "cmd", "com", "scr", "pif", "gadget", "cpl", "msc",
    # Скрипты и макросы
    "vbs", "vbe", "js", "jse", "wsf", "wsh", "ps1", "ps1xml", "ps2", "psc1", "psc2", "jar",
    # Офисные документы с макросами VBA
    "docm", "xlsm", "pptm", "dotm", "xltm", "xlam", "potm", "ppam", "sldm",
    # Системные файлы и реестр
    "reg", "inf", "hta", "dll", "sys", "apk", "app", "deb", "rpm",
    # Образы дисков
    "iso", "img", "dmg", "vhd", "vhdx",
])

MEDIUM_RISK_EXTENSIONS: frozenset[str] = frozenset([
    # Архивы (потенциальный скрытый перенос угроз)
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "cab", "ace", "arj",
    "tar.gz", "tar.bz2", "tar.xz", "backup.tar",
    # Базы данных и файлы конфигураций
    "sql", "db", "sqlite", "sqlite3", "config", "env", "ini", "cfg",
    # Серверные скрипты и код
    "php", "py", "pl", "rb", "cgi", "sh", "bash",
])

LOW_RISK_EXTENSIONS: frozenset[str] = frozenset([
    # Офисные документы и таблицы без макросов
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf",
    # Текстовые данные
    "txt", "csv", "tsv", "log", "md", "xml", "json", "yaml", "yml",
    # Графика
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "tiff", "tif",
    # Аудио
    "mp3", "wav", "ogg", "flac", "aac", "m4a", "wma",
    # Видео
    "mp4", "avi", "mkv", "mov", "wmv", "webm",
    # Электронные книги и шрифты
    "epub", "fb2", "mobi", "djvu", "ttf", "otf", "woff", "woff2",
])

# Типы файлов, доступные для прямого безопасного браузерного предпросмотра
TEXT_PREVIEW_EXTENSIONS: frozenset[str] = frozenset([
    "txt", "log", "csv", "tsv", "json", "xml", "html", "htm", "md",
    "sql", "py", "sh", "bash", "yml", "yaml", "ini", "cfg", "conf", "env",
])

IMAGE_EXTENSIONS: frozenset[str] = frozenset([
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "tiff", "tif",
])

AUDIO_EXTENSIONS: frozenset[str] = frozenset([
    "mp3", "wav", "ogg", "flac", "aac", "m4a",
])

VIDEO_EXTENSIONS: frozenset[str] = frozenset([
    "mp4", "webm", "ogg", "mov",
])


def split_filename(filename: str) -> Tuple[str, str]:
    """Разделяет имя файла на базовую часть (stem) и расширение.

    Поддерживает составные расширения вида .tar.gz, .tar.bz2 и файлы без расширения.

    Args:
        filename (str): Полное имя файла (например, 'document.docx' или 'archive.tar.gz').

    Returns:
        tuple[str, str]: Кортеж (base_name, ext_with_dot). Расширение включает точку.
            Если расширение отсутствует, возвращается (filename, '').
    """
    if not filename:
        return ("", "")

    cleaned_name = filename.strip()
    lower_name = cleaned_name.lower()

    for compound in COMPOUND_EXTENSIONS:
        if lower_name.endswith(compound):
            idx = len(cleaned_name) - len(compound)
            return (cleaned_name[:idx], cleaned_name[idx:])

    base, ext = os.path.splitext(cleaned_name)
    return (base, ext)


def get_attachment_security_info(filename: str, content_type: str = "") -> Dict[str, Any]:
    """Определяет профиль информационной безопасности и параметры UI для почтового вложения.

    Оценивает расширение файла, формирует класс риска, иконки, подсказку (tooltip),
    режим браузерного предпросмотра и укороченное имя для компактного отображения
    в две строки с гарантированным сохранением расширения.

    Args:
        filename (str): Исходное наименование файла.
        content_type (str, optional): MIME-тип из заголовков почтового сообщения.

    Returns:
        dict[str, Any]: Словарь метаданных:
            - name_base: исходное имя без расширения;
            - ext: расширение с точкой;
            - short_base: базовое имя, укороченное до 45 символов с многоточием при превышении;
            - display_name: компактное имя для вывода;
            - risk_level: 'high' | 'medium' | 'low' | 'neutral';
            - risk_label: русскоязычный бейдж риска;
            - risk_tooltip: подробное объяснение уровня риска;
            - risk_color_class: Bootstrap-класс текста цвета риска;
            - risk_badge_class: Bootstrap-класс бейджа;
            - risk_icon: Boxicons-класс значка щита;
            - file_icon: Boxicons-класс типа файла;
            - preview_type: 'pdf' | 'image' | 'text' | 'audio' | 'video' | 'unsupported';
            - can_preview_directly: True, если поддерживается прямой рендеринг в браузере.
    """
    raw_name = filename or "attachment"
    base, ext = split_filename(raw_name)
    clean_ext = ext.lstrip(".").lower()

    # Умное сокращение базового имени: если длиннее 45 символов, обрезаем и ставим '...'
    max_chars = 45
    if len(base) > max_chars:
        short_base = base[: max_chars - 3].rstrip() + "..."
    else:
        short_base = base

    display_name = f"{short_base}{ext}"

    # Оценка уровня безопасности
    if clean_ext in HIGH_RISK_EXTENSIONS:
        risk_level = "high"
        risk_label = "Высокий риск"
        risk_tooltip = (
            "Потенциально опасный тип файла (исполняемый код, скрипт или макросы VBA). "
            "Не открывайте и не запускайте, если не уверены в надежности отправителя!"
        )
        risk_color_class = "text-danger"
        risk_badge_class = "badge bg-danger text-white"
        risk_icon = "bx bxs-shield-x"
    elif clean_ext in MEDIUM_RISK_EXTENSIONS:
        risk_level = "medium"
        risk_label = "Внимание"
        risk_tooltip = (
            "Повышенное внимание: архив или файл конфигурации/кода. "
            "Рекомендуется проверить содержимое перед запуском."
        )
        risk_color_class = "text-warning"
        risk_badge_class = "badge bg-warning text-dark"
        risk_icon = "bx bxs-shield"
    elif clean_ext in LOW_RISK_EXTENSIONS:
        risk_level = "low"
        risk_label = "Безопасный"
        risk_tooltip = "Безопасный формат: стандартный офисный документ или медиафайл."
        risk_color_class = "text-success"
        risk_badge_class = "badge bg-success text-white"
        risk_icon = "bx bxs-check-shield"
    else:
        risk_level = "neutral"
        risk_label = "Нейтральный"
        risk_tooltip = "Нестандартный или редкий формат файла. Соблюдайте общие меры предосторожности."
        risk_color_class = "text-muted"
        risk_badge_class = "badge bg-secondary text-white"
        risk_icon = "bx bx-shield"

    # Иконка файла и режим предпросмотра
    c_type = (content_type or "").lower()
    if clean_ext == "pdf" or c_type == "application/pdf":
        file_icon = "bx bxs-file-pdf text-danger"
        preview_type = "pdf"
        can_preview_directly = True
    elif clean_ext in IMAGE_EXTENSIONS or c_type.startswith("image/"):
        file_icon = "bx bx-image text-info"
        preview_type = "image"
        can_preview_directly = True
    elif clean_ext in ("doc", "docx", "odt", "rtf"):
        file_icon = "bx bxs-file-doc text-primary"
        preview_type = "unsupported"
        can_preview_directly = False
    elif clean_ext in ("xls", "xlsx", "ods", "xlsm", "xltm", "xlam"):
        file_icon = "bx bxs-spreadsheet text-success"
        preview_type = "unsupported"
        can_preview_directly = False
    elif clean_ext in ("ppt", "pptx", "odp", "pptm"):
        file_icon = "bx bxs-file text-warning"
        preview_type = "unsupported"
        can_preview_directly = False
    elif clean_ext in ("zip", "rar", "7z", "tar", "gz", "bz2", "xz", "cab", "iso", "tar.gz", "tar.bz2", "tar.xz", "backup.tar"):
        file_icon = "bx bxs-file-archive text-warning"
        preview_type = "unsupported"
        can_preview_directly = False
    elif clean_ext in AUDIO_EXTENSIONS or c_type.startswith("audio/"):
        file_icon = "bx bx-music text-primary"
        preview_type = "audio"
        can_preview_directly = True
    elif clean_ext in VIDEO_EXTENSIONS or c_type.startswith("video/"):
        file_icon = "bx bx-video text-danger"
        preview_type = "video"
        can_preview_directly = True
    elif clean_ext in TEXT_PREVIEW_EXTENSIONS or c_type.startswith("text/"):
        file_icon = "bx bx-file-blank text-secondary"
        preview_type = "text"
        can_preview_directly = True
    elif clean_ext in HIGH_RISK_EXTENSIONS:
        file_icon = "bx bx-terminal text-danger"
        preview_type = "unsupported"
        can_preview_directly = False
    else:
        file_icon = "bx bx-file text-primary"
        preview_type = "unsupported"
        can_preview_directly = False

    return {
        "name_base": base,
        "ext": ext,
        "short_base": short_base,
        "display_name": display_name,
        "risk_level": risk_level,
        "risk_label": risk_label,
        "risk_tooltip": risk_tooltip,
        "risk_color_class": risk_color_class,
        "risk_badge_class": risk_badge_class,
        "risk_icon": risk_icon,
        "file_icon": file_icon,
        "preview_type": preview_type,
        "can_preview_directly": can_preview_directly,
    }


def enrich_attachment_dict(att: Dict[str, Any]) -> Dict[str, Any]:
    """Обогащает словарь вложения метаданными безопасности и форматирования.

    Модифицирует переданный словарь in-place и возвращает его.

    Args:
        att (dict[str, Any]): Исходный словарь вложения (part_index, filename, content_type...).

    Returns:
        dict[str, Any]: Обогащенный словарь с ключами безопасности и UI.
    """
    fname = att.get("filename", "")
    ctype = att.get("content_type", "")
    sec_info = get_attachment_security_info(fname, ctype)
    att.update(sec_info)
    return att
