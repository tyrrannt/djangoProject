"""Маршруты URL для приложения корпоративной почты mailbox_app."""

from django.urls import path
from mailbox_app import views

app_name = "mailbox_app"

urlpatterns = [
    # Главная страница почты (Папка Входящие)
    path("", views.MailboxFolderView.as_view(), name="index"),
    # Просмотр конкретной папки
    path("folder/<path:folder>/", views.MailboxFolderView.as_view(), name="folder"),
    # Просмотр письма
    path("folder/<path:folder>/email/<int:uid>/", views.MailboxEmailDetailView.as_view(), name="email_detail"),
    # Написание нового письма
    path("compose/", views.MailboxComposeView.as_view(), name="compose"),
    # Скачивание вложения
    path(
        "folder/<path:folder>/email/<int:uid>/attachment/<int:part_index>/",
        views.MailboxAttachmentDownloadView.as_view(),
        name="download_attachment",
    ),
    # AJAX API действий (прочитано, удаление, звездочка)
    path("api/action/", views.MailboxActionAPIView.as_view(), name="api_action"),
    # AJAX API адресной книги сотрудников
    path("api/contacts/", views.MailboxContactsAPIView.as_view(), name="api_contacts"),
    # Настройки почты и подписи
    path("settings/", views.MailboxSettingsView.as_view(), name="settings"),
    # Профилирование и диагностика производительности
    path("diag/", views.MailboxDiagnosticView.as_view(), name="diag"),
]
