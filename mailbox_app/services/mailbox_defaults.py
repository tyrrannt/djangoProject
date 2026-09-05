"""Централизованные параметры подключения по умолчанию для почтовых ящиков.

Содержит шаблоны настроек для корпоративного домена barkol.ru и популярных
сторонних почтовых сервисов (Яндекс, Mail.ru, Gmail).
"""

from typing import Any, Dict

DEFAULT_DOMAIN: str = "barkol.ru"

DOMAIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "barkol.ru": {
        "domain": "barkol.ru",
        "description": "Основной почтовый сервер ООО 'Баркол'",
        "incoming_protocol": "imap",
        "imap_host": "imap.barkol.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "sm.barkol.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "yandex.ru": {
        "domain": "yandex.ru",
        "description": "Яндекс 360 / Яндекс Почта",
        "incoming_protocol": "imap",
        "imap_host": "imap.yandex.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.yandex.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "mail.ru": {
        "domain": "mail.ru",
        "description": "VK WorkSpace / Mail.ru",
        "incoming_protocol": "imap",
        "imap_host": "imap.mail.ru",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.mail.ru",
        "smtp_port": 465,
        "smtp_security": "ssl",
    },
    "gmail.com": {
        "domain": "gmail.com",
        "description": "Google Workspace / Gmail",
        "incoming_protocol": "imap",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
    },
}


def get_domain_defaults(domain: str) -> Dict[str, Any]:
    """Возвращает параметры подключения по умолчанию для указанного домена.

    Если домен отсутствует в пресетах, возвращает настройки по умолчанию для barkol.ru.

    Args:
        domain (str): Имя домена почты (например, 'barkol.ru' или 'gmail.com').

    Returns:
        Dict[str, Any]: Словарь с параметрами IMAP и SMTP.

    Example:
        >>> defaults = get_domain_defaults("barkol.ru")
        >>> defaults["imap_host"]
        'imap.barkol.ru'
    """
    clean_domain = (domain or "").strip().lower()
    return DOMAIN_PRESETS.get(clean_domain, DOMAIN_PRESETS[DEFAULT_DOMAIN]).copy()


def get_all_presets() -> Dict[str, Dict[str, Any]]:
    """Возвращает все зарегистрированные пресеты почтовых доменов.

    Returns:
        Dict[str, Dict[str, Any]]: Словарь всех пресетов.
    """
    return DOMAIN_PRESETS.copy()


def generate_corporate_signature(user, account=None) -> str:
    """Генерирует аккуратную официальную HTML-подпись авиакомпании «БАРКОЛ».

    Формирует строгую блочно-табличную подпись сотрудника для исходящих писем,
    соответствующую корпоративному стилю авиакомпании «БАРКОЛ»:
    - Приветствие («С уважением,»);
    - Без лишних горизонтальных линий и рамок;
    - Слева: официальный логотип авиакомпании «БАРКОЛ»;
    - Вертикальная синяя разделительная полоса (#0088cc);
    - Справа:
      - ФИО сотрудника полужирным шрифтом (14px, #0f172a);
      - Должность сотрудника (12px, #64748b);
      - Наименование подразделения (11.5px, #64748b);
      - ООО Авиакомпания «БАРКОЛ» синим полужирным цветом (12px, #0088cc);
      - Корпоративный email со ссылкой mailto;
      - Адрес официального сайта www.barkol.ru со ссылкой https://barkol.ru;
    - Адаптивный рендеринг для десктопных и мобильных почтовых клиентов.

    Args:
        user: Экземпляр модели DataBaseUser (текущий авторизованный пользователь).
        account (MailAccount, optional): Активный почтовый аккаунт отправителя.

    Returns:
        str: Готовая HTML-разметка корпоративной подписи.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return ""

    # Определение ФИО
    last_name = getattr(user, "last_name", "") or ""
    first_name = getattr(user, "first_name", "") or ""
    surname = getattr(user, "surname", "") or ""
    last_name = last_name.strip()
    first_name = first_name.strip()
    surname = surname.strip()

    if last_name and first_name:
        full_name = f"{last_name} {first_name} {surname}".strip()
    else:
        full_name = getattr(user, "title", "").strip() or getattr(user, "username", "")

    # Определение должности и подразделения
    job_title = ""
    division_name = ""
    work_profile = getattr(user, "user_work_profile", None)
    if work_profile:
        if getattr(work_profile, "job", None):
            job_title = str(work_profile.job).strip()
        if getattr(work_profile, "divisions", None):
            division_name = str(work_profile.divisions).strip()

    if not job_title and hasattr(user, "job") and user.job:
        job_title = str(user.job).strip()

    # Определение корпоративного email
    email = ""
    if account and getattr(account, "email", None):
        email = account.email.strip()
    elif getattr(user, "email", None):
        email = user.email.strip()

    job_html = f'<div style="color: #64748b; font-size: 12px; margin: 0 0 2px 0; line-height: 1.35;">{job_title}</div>' if job_title else ""
    division_html = ""
    if division_name and division_name.strip().lower() != job_title.strip().lower():
        division_html = f'<div style="color: #64748b; font-size: 11.5px; margin: 0 0 2px 0; line-height: 1.35;">{division_name}</div>'

    email_html = ""
    if email:
        email_html = f'<div style="color: #64748b; font-size: 11.5px; margin-top: 2px; line-height: 1.35;">e-mail: <a href="mailto:{email}" style="color: #0088cc; text-decoration: none;">{email}</a></div>'

    signature_html = (
        f'<div class="barkol-email-signature" style="font-family: Arial, Helvetica, sans-serif; font-size: 13px; color: #1e293b; line-height: 1.45; margin-top: 20px; border: none; padding: 0;">\n'
        f'    <p style="margin: 0 0 12px 0; color: #475569; font-size: 13px; font-family: Arial, Helvetica, sans-serif;">С уважением,</p>\n'
        f'    <table cellpadding="0" cellspacing="0" border="0" style="border-collapse: collapse; border: none; margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; width: auto; max-width: 100%;">\n'
        f'        <tbody>\n'
        f'            <tr>\n'
        f'                <td style="padding: 0 16px 0 0; vertical-align: middle; border: none; text-align: center; width: 125px;">\n'
        f'                    <a href="https://barkol.ru" target="_blank" style="text-decoration: none; border: none;" title="ООО Авиакомпания «БАРКОЛ»">\n'
        f'                        <img src="https://corp.barkol.ru/static/logo_small.png" alt="ООО Авиакомпания «БАРКОЛ»" width="120" style="display: block; width: 120px; max-width: 120px; height: auto; border: 0; outline: none; text-decoration: none;" />\n'
        f'                    </a>\n'
        f'                </td>\n'
        f'                <td style="padding: 0 0 0 16px; vertical-align: middle; border-left: 2px solid #0088cc; border-top: none; border-right: none; border-bottom: none; font-family: Arial, Helvetica, sans-serif;">\n'
        f'                    <div style="font-weight: 700; font-size: 14px; color: #0f172a; margin: 0 0 2px 0; line-height: 1.3;">{full_name}</div>\n'
        f'                    {job_html}\n'
        f'                    {division_html}\n'
        f'                    <div style="color: #0088cc; font-weight: 700; font-size: 12px; margin: 3px 0 2px 0; line-height: 1.3;">ООО Авиакомпания «БАРКОЛ»</div>\n'
        f'                    {email_html}\n'
        f'                    <div style="margin-top: 2px; font-size: 11.5px; line-height: 1.3;">\n'
        f'                        <a href="https://barkol.ru" target="_blank" style="color: #0088cc; text-decoration: none; font-weight: 500;">www.barkol.ru</a>\n'
        f'                    </div>\n'
        f'                </td>\n'
        f'            </tr>\n'
        f'        </tbody>\n'
        f'    </table>\n'
        f'</div>'
    )
    return signature_html
