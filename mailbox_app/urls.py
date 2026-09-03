"""Маршруты URL для приложения корпоративной почты mailbox_app."""

from django.urls import path
from mailbox_app import views

app_name = "mailbox_app"

urlpatterns = [
    # Главная страница почты (Папка Входящие)
    path("", views.MailboxFolderView.as_view(), name="index"),
    # Скачивание вложения (должно быть выше общего folder)
    path(
        "folder/<path:folder>/email/<int:uid>/attachment/<int:part_index>/",
        views.MailboxAttachmentDownloadView.as_view(),
        name="download_attachment",
    ),
    # Скачивание всех вложений архивом ZIP
    path(
        "folder/<path:folder>/email/<int:uid>/attachments/zip/",
        views.MailboxDownloadAttachmentsZipView.as_view(),
        name="download_all_attachments_zip",
    ),
    # Печать официального бланка письма
    path(
        "folder/<path:folder>/email/<int:uid>/print/",
        views.MailboxPrintLetterheadView.as_view(),
        name="print_letterhead",
    ),
    # Просмотр письма (должен быть выше общего folder)
    path(
        "folder/<path:folder>/email/<int:uid>/",
        views.MailboxEmailDetailView.as_view(),
        name="email_detail",
    ),
    # Написание нового письма
    path("compose/", views.MailboxComposeView.as_view(), name="compose"),
    # Реестр адресной книги и управление контактами
    path("contacts/", views.MailboxContactsListView.as_view(), name="contacts_list"),
    path("contacts/save/", views.MailboxContactCreateOrUpdateView.as_view(), name="contact_save"),
    path("contacts/<int:pk>/delete/", views.MailboxContactDeleteView.as_view(), name="contact_delete"),
    # Список писем, запланированных к отправке по расписанию
    path("scheduled/", views.MailboxScheduledListView.as_view(), name="scheduled_list"),
    # Детальный просмотр запланированного письма
    path("scheduled/<int:pk>/", views.MailboxScheduledDetailView.as_view(), name="scheduled_detail"),
    # Редактирование запланированного письма
    path("scheduled/<int:pk>/edit/", views.MailboxScheduledEditView.as_view(), name="scheduled_edit"),
    # Скачивание вложения запланированного письма
    path(
        "scheduled/<int:pk>/attachment/<int:att_id>/",
        views.MailboxScheduledAttachmentDownloadView.as_view(),
        name="scheduled_attachment_download",
    ),
    # AJAX API управления запланированными письмами
    path(
        "api/scheduled/action/",
        views.MailboxScheduledActionAPIView.as_view(),
        name="api_scheduled_action",
    ),
    # AJAX API автосохранения и сохранения черновиков
    path("api/draft/save/", views.MailboxSaveDraftAPIView.as_view(), name="api_save_draft"),
    # Администрирование корпоративных почтовых ящиков
    path("admin/mailboxes/", views.MailboxAdminListView.as_view(), name="mailbox_admin_list"),
    path("admin/mailboxes/create/", views.MailboxAdminCreateView.as_view(), name="mailbox_admin_create"),
    path("admin/mailboxes/<int:pk>/edit/", views.MailboxAdminUpdateView.as_view(), name="mailbox_admin_edit"),
    path("admin/mailboxes/<int:pk>/toggle/", views.MailboxAdminToggleActiveView.as_view(), name="mailbox_admin_toggle"),
    path("admin/mailboxes/<int:pk>/delete/", views.MailboxAdminDeleteView.as_view(), name="mailbox_admin_delete"),
    path("admin/print-settings/", views.MailboxPrintSettingsAdminView.as_view(), name="admin_print_settings"),
    path("api/mailbox/test-connection/", views.MailboxTestConnectionAPIView.as_view(), name="api_mailbox_test_connection"),
    path("api/mailbox/domain-defaults/", views.MailboxDomainPresetAPIView.as_view(), name="api_mailbox_domain_defaults"),
    # AJAX API шаблонов ответов / писем
    path("api/templates/", views.MailboxTemplatesAPIView.as_view(), name="api_templates"),
    path("api/templates/<int:pk>/", views.MailboxTemplatesAPIView.as_view(), name="api_template_detail"),
    # Просмотр конкретной папки (жадный path:folder)
    path("folder/<path:folder>/", views.MailboxFolderView.as_view(), name="folder"),
    # AJAX API действий (прочитано, удаление, звездочка)
    path("api/action/", views.MailboxActionAPIView.as_view(), name="api_action"),
    # AJAX API адресной книги сотрудников
    path("api/contacts/", views.MailboxContactsAPIView.as_view(), name="api_contacts"),
    # AJAX API проверки непрочитанных писем и уведомлений
    path("api/unread_count/", views.MailboxUnreadCountAPIView.as_view(), name="api_unread_count"),
    # Настройки почты и подписи
    path("settings/", views.MailboxSettingsView.as_view(), name="settings"),
    # Профилирование и диагностика производительности
    path("diag/", views.MailboxDiagnosticView.as_view(), name="diag"),
]
