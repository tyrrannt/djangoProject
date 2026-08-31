"""Сервис управления и автоконфигурации учетных записей почты пользователей."""

import logging
from typing import Optional

from django.conf import settings
from mailbox_app.models import MailAccount

logger = logging.getLogger(__name__)


def get_user_mail_account(user) -> Optional[MailAccount]:
    """Возвращает или автоматически инициализирует почтовый аккаунт для пользователя.

    Email пользователя считывается из DataBaseUser.email (или username),
    а пароль — из DataBaseUserWorkProfile.work_email_password.

    Args:
        user (DataBaseUser): Авторизованный пользователь.

    Returns:
        MailAccount, optional: Объект почтового аккаунта или None, если почта не настроена.
    """
    if not user.is_authenticated:
        return None

    # 1. Извлекаем пароль из рабочего профиля пользователя
    work_profile = getattr(user, "user_work_profile", None)
    profile_password = ""
    if work_profile:
        profile_password = (
            getattr(work_profile, "work_email_password", "")
            or getattr(work_profile, "work_application_password", "")
            or ""
        ).strip()

    # 2. Извлекаем email пользователя
    user_email = (getattr(user, "email", "") or "").strip()
    if not user_email and "@" in getattr(user, "username", ""):
        user_email = user.username.strip()

    # 3. Проверяем существующий аккаунт в базе данных
    account = getattr(user, "mail_account", None)
    if account:
        needs_save = False
        if user_email and account.email != user_email:
            account.email = user_email
            needs_save = True
        # Если в аккаунте пароль пустой или изменился в профиле — синхронизируем
        if profile_password and account.get_password() != profile_password:
            account.set_password(profile_password)
            needs_save = True
        if needs_save:
            account.save()
        return account

    # 4. Если аккаунта еще нет — создаем новый
    if not user_email:
        return None

    display_name = (
        f"{user.last_name} {user.first_name} {user.surname or ''}".strip()
        or user.username
    )
    imap_host = getattr(settings, "EMAIL_IMAP_HOST", "imap.barkol.ru")
    smtp_host = getattr(settings, "EMAIL_HOST", "sm.barkol.ru")

    account = MailAccount.objects.create(
        user=user,
        email=user_email,
        display_name=display_name,
        imap_host=imap_host,
        imap_port=993,
        imap_use_ssl=True,
        smtp_host=smtp_host,
        smtp_port=465,
        smtp_use_ssl=True,
        smtp_use_tls=False,
    )
    if profile_password:
        account.set_password(profile_password)
        account.save(update_fields=["encrypted_password"])

    logger.info(f"[Mailbox] Создан почтовый аккаунт для {user} ({user_email})")
    return account
