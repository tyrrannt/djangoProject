"""Пакет интеграции и администрирования почтового сервера Kerio Connect 9.4.1."""

from mailbox_app.services.kerio.client import KerioConnectAdminClient
from mailbox_app.services.kerio.domains import DomainManager
from mailbox_app.services.kerio.exceptions import (
    KerioAPIError,
    KerioAuthenticationError,
    KerioConnectionError,
    KerioObjectNotFoundError,
    KerioSessionExpired,
    KerioValidationError,
)
from mailbox_app.services.kerio.external_provider import (
    BaseExternalMailProvider,
    ISPmanagerExternalMailProvider,
    ManualExternalMailProvider,
    RegRuExternalMailProvider,
)
from mailbox_app.services.kerio.pop3_download import Pop3DownloadManager
from mailbox_app.services.kerio.service import KerioAdminService
from mailbox_app.services.kerio.smtp_delivery import SmtpDeliveryManager
from mailbox_app.services.kerio.users import UserManager
from mailbox_app.services.kerio.utils import (
    generate_corporate_mailbox_login,
    parse_fio_components,
    transliterate_ru_to_en,
)

__all__ = [
    "KerioConnectAdminClient",
    "DomainManager",
    "UserManager",
    "Pop3DownloadManager",
    "SmtpDeliveryManager",
    "KerioAdminService",
    "BaseExternalMailProvider",
    "ManualExternalMailProvider",
    "RegRuExternalMailProvider",
    "ISPmanagerExternalMailProvider",
    "KerioAPIError",
    "KerioConnectionError",
    "KerioAuthenticationError",
    "KerioSessionExpired",
    "KerioValidationError",
    "KerioObjectNotFoundError",
    "transliterate_ru_to_en",
    "parse_fio_components",
    "generate_corporate_mailbox_login",
]
