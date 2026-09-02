"""Представления (Views) приложения корпоративной веб-почты."""

import email
from email.utils import parseaddr
import html
import imaplib
import json
import logging
import re
import socket
import ssl
import time
from typing import Optional
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from customers_app.models import DataBaseUser
from mailbox_app.forms import MailAccountSettingsForm, MailComposeForm, ScheduledEmailEditForm
from mailbox_app.models import (
    MailAccount,
    MailContact,
    ScheduledEmail,
    ScheduledEmailAttachment,
)
from mailbox_app.services.account_service import get_user_mail_account
from mailbox_app.services.imap_service import (
    ImapMailService,
    decode_imap_utf7,
    invalidate_mailbox_cache,
)
from mailbox_app.services.smtp_service import SmtpMailService

logger = logging.getLogger(__name__)


class MailboxBaseMixin(LoginRequiredMixin):
    """Базовый миксин для представлений почты: проверка и получение почтового аккаунта."""

    def get_account(self) -> Optional[MailAccount]:
        """Возвращает или настраивает почтовый аккаунт для текущего пользователя.

        Returns:
            MailAccount, optional: Объект почтового ящика или None.
        """
        try:
            return get_user_mail_account(self.request.user)
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка получения почтового аккаунта для {self.request.user}: {e}")
            return None

    def get_imap_service(self, account: MailAccount) -> ImapMailService:
        """Создает и возвращает экземпляр IMAP-сервиса.

        Args:
            account (MailAccount): Почтовый аккаунт.

        Returns:
            ImapMailService: Сервис подключения к IMAP.
        """
        return ImapMailService(
            host=account.imap_host,
            port=account.imap_port,
            email_addr=account.email,
            password=account.get_password(),
            use_ssl=account.imap_use_ssl,
        )

    def get_scheduled_count(self) -> int:
        """Возвращает количество активных запланированных писем текущего пользователя.

        Returns:
            int: Количество писем в статусе 'pending'.
        """
        try:
            from mailbox_app.models import ScheduledEmail

            return ScheduledEmail.objects.filter(
                user=self.request.user,
                status=ScheduledEmail.STATUS_PENDING,
            ).count()
        except Exception:
            return 0


class MailboxFolderView(MailboxBaseMixin, TemplateView):
    """Представление для отображения списка писем выбранной папки."""

    template_name = "mailbox_app/folder.html"

    def get_context_data(self, **kwargs):
        """Формирует контекст данных для списка писем и дерева папок.

        Returns:
            dict: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()

        current_folder = self.kwargs.get("folder", "INBOX")
        search_query = self.request.GET.get("q", "").strip()
        q_scope = self.request.GET.get("scope", "all").strip().lower()
        date_range = self.request.GET.get("date_range", "all").strip().lower()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        sort_by = self.request.GET.get("sort", "date").strip().lower()
        sort_dir = self.request.GET.get("dir", "desc").strip().lower()
        filter_by = self.request.GET.get("filter", "all").strip().lower()
        page = int(self.request.GET.get("page", 1))
        force_refresh = bool(self.request.GET.get("refresh"))
        per_page = 25

        folders = []
        email_messages = []
        total_count = 0
        error_message = None

        if account and account.email:
            password = account.get_password()
            if not password:
                error_message = (
                    "Пароль от корпоративной почты не задан в профиле пользователя. "
                    "Пожалуйста, укажите пароль в настройках почты или обратитесь в отдел IT."
                )
            else:
                email_clean = account.email.strip().lower()
                if force_refresh:
                    invalidate_mailbox_cache(email_clean)

                try:
                    with self.get_imap_service(account) as imap_svc:
                        folders = imap_svc.get_folders(force_refresh=force_refresh)
                        email_messages, total_count = imap_svc.get_messages(
                            folder_name=current_folder,
                            page=page,
                            per_page=per_page,
                            query=search_query if search_query else None,
                            sort_by=sort_by,
                            sort_dir=sort_dir,
                            filter_by=filter_by,
                            force_refresh=force_refresh,
                            q_scope=q_scope,
                            date_range=date_range,
                            date_from=date_from,
                            date_to=date_to,
                        )
                except Exception as e:
                    logger.error(f"[Mailbox] Ошибка загрузки писем из {current_folder}: {e}")
                    error_message = f"Не удалось подключиться к серверу IMAP: {e}"
        else:
            error_message = (
                "Корпоративный почтовый ящик не настроен для вашей учетной записи (не указан корпоративный Email адрес). "
                "Пожалуйста, обратитесь к системному администратору или в отдел кадров."
            )

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        current_type = "custom"
        current_folder_display = decode_imap_utf7(current_folder)
        for f in folders:
            if f.get("raw_name") == current_folder:
                current_type = f.get("type", "custom")
                current_folder_display = f.get("full_path_display") or f.get("display_name", current_folder_display)
                break
        is_junk = current_type in ("junk", "spam") or any(s in current_folder.lower() for s in ("junk", "спам", "spam"))

        cf_lower = current_folder.lower()
        is_sent = (
            current_type == "sent"
            or any(f.get("raw_name") == current_folder and f.get("root_type") == "sent" for f in folders)
            or any(s in cf_lower for s in ("sent", "отправленн"))
        )
        is_drafts = (
            current_type == "drafts"
            or any(f.get("raw_name") == current_folder and f.get("root_type") == "drafts" for f in folders)
            or any(s in cf_lower for s in ("draft", "черновик"))
        )
        show_recipient = is_sent or is_drafts

        recipient_label = "получателю" if show_recipient else "автору"
        sort_labels = {
            ("date", "desc"): "По дате (сначала новые)",
            ("date", "asc"): "По дате (сначала старые)",
            ("from", "asc"): f"По {recipient_label} (А → Я)",
            ("from", "desc"): f"По {recipient_label} (Я → А)",
            ("to", "asc"): "По получателю (А → Я)",
            ("to", "desc"): "По получателю (Я → А)",
            ("subject", "asc"): "По теме (А → Я)",
            ("subject", "desc"): "По теме (Я → А)",
            ("size", "desc"): "По размеру (убывание)",
            ("size", "asc"): "По размеру (возрастание)",
            ("flagged", "desc"): "Сначала важные",
            ("flagged", "asc"): "Сначала обычные",
            ("unread", "desc"): "Сначала непрочитанные",
            ("unread", "asc"): "Сначала прочитанные",
            ("attachments", "desc"): "Сначала с вложениями",
            ("attachments", "asc"): "Сначала без вложений",
        }
        current_sort_label = sort_labels.get((sort_by, sort_dir), "По дате (сначала новые)")

        # Формируем query_params без page для корректной пагинации
        query_dict = self.request.GET.copy()
        if "page" in query_dict:
            query_dict.pop("page")
        extra_query = query_dict.urlencode()
        query_prefix = f"&{extra_query}" if extra_query else ""

        # Формируем параметры для сохранения поиска и диапазона дат при переключении сортировки/статусов
        filter_dict = self.request.GET.copy()
        for k in ("page", "refresh", "filter", "sort", "dir"):
            filter_dict.pop(k, None)
        filter_extra = filter_dict.urlencode()
        filter_query_params = f"&{filter_extra}" if filter_extra else ""

        date_range_labels = {
            "all": "",
            "today": "За сегодня",
            "week": "За последнюю неделю",
            "month": "За последний месяц",
            "custom": f"Период: {date_from or '...'} — {date_to or '...'}",
        }
        date_range_display = date_range_labels.get(date_range, "")

        scope_labels = {
            "all": "Везде (тема, автор, текст)",
            "headers": "Тема и автор",
            "body": "Текст сообщения (BODY)",
        }
        scope_display = scope_labels.get(q_scope, "")

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {"name": "Корпоративная почта", "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"})},
                {"name": current_folder_display},
            ],
            "account": account,
            "folders": folders,
            "current_folder": current_folder,
            "current_folder_display": current_folder_display,
            "current_folder_type": current_type,
            "is_junk": is_junk,
            "is_sent": is_sent,
            "is_drafts": is_drafts,
            "show_recipient": show_recipient,
            "scheduled_count": self.get_scheduled_count(),
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "filter_by": filter_by,
            "current_sort_label": current_sort_label,
            "query_prefix": query_prefix,
            "filter_query_params": filter_query_params,
            "messages_list": email_messages,
            "total_count": total_count,
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "search_query": search_query,
            "q_scope": q_scope,
            "scope_display": scope_display,
            "date_range": date_range,
            "date_range_display": date_range_display,
            "date_from": date_from,
            "date_to": date_to,
            "error_message": error_message,
        })
        return context


class MailboxEmailDetailView(MailboxBaseMixin, TemplateView):
    """Представление для детального просмотра письма."""

    template_name = "mailbox_app/email_detail.html"

    def get_context_data(self, **kwargs):
        """Загружает полное содержимое письма с сервера IMAP.

        Returns:
            dict: Контекст с данными письма.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folder_name = self.kwargs.get("folder", "INBOX")
        uid = int(self.kwargs.get("uid"))

        email_data = None
        folders = []
        error_message = None

        try:
            with self.get_imap_service(account) as imap_svc:
                email_data = imap_svc.get_message_detail(folder_name, uid)
                folders = imap_svc.get_folders(force_refresh=True)
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка загрузки письма {uid}: {e}")
            error_message = str(e)

        if not email_data and not error_message:
            raise Http404("Письмо не найдено или было удалено.")

        current_type = "custom"
        current_folder_display = decode_imap_utf7(folder_name)
        for f in folders:
            if f.get("raw_name") == folder_name:
                current_type = f.get("type", "custom")
                current_folder_display = f.get("full_path_display") or f.get("display_name", current_folder_display)
                break
        is_junk = current_type in ("junk", "spam") or any(s in folder_name.lower() for s in ("junk", "спам", "spam"))

        fn_lower = folder_name.lower()
        is_sent = (
            current_type == "sent"
            or any(f.get("raw_name") == folder_name and f.get("root_type") == "sent" for f in folders)
            or any(s in fn_lower for s in ("sent", "отправленн"))
        )
        is_drafts = (
            current_type == "drafts"
            or any(f.get("raw_name") == folder_name and f.get("root_type") == "drafts" for f in folders)
            or any(s in fn_lower for s in ("draft", "черновик"))
        )
        if is_drafts and email_data:
            return redirect(f"{reverse('mailbox_app:compose')}?draft_uid={uid}&folder={quote(folder_name)}")

        show_recipient = is_sent or is_drafts

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {"name": "Корпоративная почта", "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"})},
                {"name": current_folder_display, "url": reverse("mailbox_app:folder", kwargs={"folder": folder_name})},
                {"name": "Просмотр письма"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": folder_name,
            "current_folder_display": current_folder_display,
            "current_folder_type": current_type,
            "is_junk": is_junk,
            "is_sent": is_sent,
            "is_drafts": is_drafts,
            "show_recipient": show_recipient,
            "scheduled_count": self.get_scheduled_count(),
            "email": email_data,
            "error_message": error_message,
        })
        return context


class MailboxComposeView(MailboxBaseMixin, FormView):
    """Представление для написания и отправки письма."""

    template_name = "mailbox_app/compose.html"
    form_class = MailComposeForm

    def get_initial(self):
        """Предзаполняет поля формы при ответе (Reply) или пересылке (Forward).

        Returns:
            dict: Начальные значения формы.
        """
        initial = super().get_initial()
        account = self.get_account()

        reply_uid = self.request.GET.get("reply_uid")
        forward_uid = self.request.GET.get("forward_uid")
        folder = self.request.GET.get("folder", "INBOX")
        to_param = self.request.GET.get("to", "")

        if to_param:
            initial["to"] = to_param

        # Автоматическая подпись
        signature = account.signature_html or ""
        if signature:
            if "<br" not in signature.lower() and "<p" not in signature.lower():
                signature = signature.replace("\n", "<br>")
            initial["body_html"] = f"<br><br>--<br>{signature}"

        draft_uid = self.request.GET.get("draft_uid")
        if draft_uid and str(draft_uid).isdigit():
            try:
                target_uid = int(draft_uid)
                with self.get_imap_service(account) as imap_svc:
                    draft_mail = imap_svc.get_message_detail(folder, target_uid)
                    if draft_mail:
                        initial["to"] = draft_mail.get("to_raw") or ""
                        initial["cc"] = draft_mail.get("cc_raw") or ""
                        initial["bcc"] = draft_mail.get("bcc_raw") or ""
                        initial["subject"] = draft_mail.get("subject") or ""
                        initial["body_html"] = draft_mail.get("body_html") or draft_mail.get("body_text") or ""
            except Exception as e:
                logger.warning(f"[Mailbox] Ошибка загрузки черновика: {e}")

        if reply_uid or forward_uid:
            target_uid = int(reply_uid or forward_uid)
            try:
                with self.get_imap_service(account) as imap_svc:
                    original_mail = imap_svc.get_message_detail(folder, target_uid)
                    if original_mail:
                        orig_subj = original_mail["subject"]
                        orig_from = original_mail["from_email"] or original_mail["from_name"]
                        orig_date = original_mail["date_raw"]
                        orig_body = original_mail["body_html"] or html.escape(original_mail["body_text"])

                        quote_block = (
                            f"<br><br><hr><blockquote>"
                            f"<b>От:</b> {html.escape(original_mail['from_raw'])}<br>"
                            f"<b>Дата:</b> {html.escape(orig_date)}<br>"
                            f"<b>Тема:</b> {html.escape(orig_subj)}<br><br>"
                            f"{orig_body}</blockquote>"
                        )

                        if reply_uid:
                            initial["to"] = orig_from
                            initial["subject"] = orig_subj if orig_subj.startswith("Re:") else f"Re: {orig_subj}"
                            initial["body_html"] = f"<br><br>{quote_block}"
                        elif forward_uid:
                            initial["subject"] = orig_subj if orig_subj.startswith("Fwd:") else f"Fwd: {orig_subj}"
                            initial["body_html"] = f"<br><br>{quote_block}"
            except Exception as e:
                logger.warning(f"[Mailbox] Ошибка при подготовке ответа: {e}")

        return initial

    def get_context_data(self, **kwargs):
        """Добавляет список папок и draft_uid в контекст формы написания письма.

        Returns:
            dict: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folders = []
        try:
            with self.get_imap_service(account) as imap_svc:
                folders = imap_svc.get_folders()
        except Exception:
            pass

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {"name": "Корпоративная почта", "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"})},
                {"name": "Новое сообщение"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": "compose",
            "scheduled_count": self.get_scheduled_count(),
            "draft_uid": self.request.GET.get("draft_uid", ""),
        })
        return context

    def form_valid(self, form):
        """Обрабатывает отправку письма сразу через SMTP или планирует отправку по расписанию.

        Args:
            form (MailComposeForm): Валидированная форма.

        Returns:
            HttpResponse: Редирект на список писем с сообщением об успехе.
        """
        account = self.get_account()
        to_raw = form.cleaned_data["to"]
        cc_raw = form.cleaned_data.get("cc", "")
        bcc_raw = form.cleaned_data.get("bcc", "")
        subject = form.cleaned_data.get("subject", "(Без темы)")
        body_html = form.cleaned_data.get("body_html", "")
        send_mode = form.cleaned_data.get("send_mode") or "now"
        scheduled_at = form.cleaned_data.get("scheduled_at")
        draft_uid_val = self.request.POST.get("draft_uid")

        # Если выбрана отправка по расписанию
        if send_mode == "scheduled" and scheduled_at:
            from mailbox_app.services.scheduled_mail_service import create_scheduled_email

            uploaded_files = self.request.FILES.getlist("attachments")
            try:
                scheduled_email = create_scheduled_email(
                    user=self.request.user,
                    account=account,
                    to_recipients=to_raw,
                    scheduled_at=scheduled_at,
                    subject=subject,
                    body_html=body_html,
                    body_text="",
                    cc_recipients=cc_raw,
                    bcc_recipients=bcc_raw,
                    uploaded_files=uploaded_files,
                )
                if draft_uid_val and str(draft_uid_val).isdigit():
                    try:
                        with self.get_imap_service(account) as imap_svc:
                            imap_svc.delete_draft(int(draft_uid_val))
                    except Exception as d_err:
                        logger.debug(f"[Mailbox] Ошибка удаления черновика: {d_err}")

                messages.success(
                    self.request,
                    f"Письмо «{subject}» успешно запланировано к отправке на {scheduled_at:%d.%m.%Y %H:%M} (МСК)!",
                )
                return redirect("mailbox_app:scheduled_list")
            except Exception as e:
                logger.error(f"[Mailbox] Ошибка создания отложенного письма: {e}", exc_info=True)
                messages.error(self.request, f"Не удалось запланировать отправку письма: {e}")
                return self.form_invalid(form)

        to_list = [addr.strip() for addr in to_raw.replace(";", ",").split(",") if addr.strip()]
        cc_list = [addr.strip() for addr in cc_raw.replace(";", ",").split(",") if addr.strip()] if cc_raw else []
        bcc_list = [addr.strip() for addr in bcc_raw.replace(";", ",").split(",") if addr.strip()] if bcc_raw else []

        # Обработка файлов вложений
        uploaded_files = self.request.FILES.getlist("attachments")
        attachments = []
        for f in uploaded_files:
            attachments.append((f.name, f.content_type, f.read()))

        smtp_service = SmtpMailService(
            smtp_host=account.smtp_host,
            smtp_port=account.smtp_port,
            email_addr=account.email,
            password=account.get_password(),
            display_name=account.display_name,
            use_ssl=account.smtp_use_ssl,
            use_tls=account.smtp_use_tls,
            imap_host=account.imap_host,
            imap_port=account.imap_port,
            imap_use_ssl=account.imap_use_ssl,
        )

        try:
            smtp_service.send_email(
                to_list=to_list,
                subject=subject,
                body_html=body_html,
                cc_list=cc_list,
                bcc_list=bcc_list,
                attachments=attachments,
            )

            # Если ранее был сохранен черновик — удаляем его из папки черновиков
            if draft_uid_val and str(draft_uid_val).isdigit():
                try:
                    with self.get_imap_service(account) as imap_svc:
                        imap_svc.delete_draft(int(draft_uid_val))
                except Exception as d_err:
                    logger.debug(f"[Mailbox] Ошибка удаления черновика после отправки: {d_err}")

            # Автоматическое сохранение контактов в адресную книгу
            try:
                from email.utils import getaddresses
                from mailbox_app.models import MailContact
                raw_recipients = f"{to_raw}, {cc_raw}, {bcc_raw}"
                for name_part, email_part in getaddresses([raw_recipients]):
                    email_clean = email_part.strip()
                    if email_clean and "@" in email_clean:
                        clean_name = name_part.strip() or email_clean.split("@")[0]
                        MailContact.objects.update_or_create(
                            user=self.request.user,
                            email=email_clean,
                            defaults={
                                "name": clean_name,
                                "source": "auto",
                            },
                        )
            except Exception as ex:
                logger.debug(f"[Mailbox] Ошибка автосохранения контакта: {ex}")

            invalidate_mailbox_cache(account.email)
            messages.success(self.request, f"Письмо «{subject}» успешно отправлено!")
            return redirect("mailbox_app:folder", folder="INBOX")
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка отправки письма: {e}")
            messages.error(self.request, f"Не удалось отправить письмо: {e}")
            return self.form_invalid(form)


class MailboxSaveDraftAPIView(MailboxBaseMixin, View):
    """AJAX API для автосохранения и ручного сохранения черновиков на IMAP сервере."""

    def post(self, request):
        """Сохраняет черновик в папку Черновики и возвращает UID.

        Returns:
            JsonResponse: Результат операции и UID сохраненного черновика.
        """
        account = self.get_account()
        if not account or not account.email or not account.get_password():
            return JsonResponse({"success": False, "error": "Аккаунт не настроен."}, status=400)

        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            data = request.POST

        to_recipients = data.get("to", "").strip()
        cc_recipients = data.get("cc", "").strip()
        bcc_recipients = data.get("bcc", "").strip()
        subject = data.get("subject", "").strip()
        body_html = data.get("body_html", "")
        old_draft_uid = data.get("draft_uid")
        old_uid_int = int(old_draft_uid) if old_draft_uid and str(old_draft_uid).isdigit() else None

        if not to_recipients and not subject and not body_html:
            return JsonResponse({"success": True, "draft_uid": old_uid_int, "empty": True})

        try:
            with self.get_imap_service(account) as imap_svc:
                new_uid = imap_svc.save_draft(
                    to_recipients=to_recipients,
                    subject=subject,
                    body_html=body_html,
                    cc_recipients=cc_recipients,
                    bcc_recipients=bcc_recipients,
                    old_draft_uid=old_uid_int,
                )
            from django.utils import timezone
            saved_time_str = timezone.now().strftime("%H:%M:%S")
            return JsonResponse({
                "success": True,
                "draft_uid": new_uid,
                "saved_at": saved_time_str,
            })
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка сохранения черновика: {e}")
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class MailboxAttachmentDownloadView(MailboxBaseMixin, View):
    """Представление для безопасного скачивания или инлайн-просмотра файла-вложения."""

    def get(self, request, folder, uid, part_index):
        """Извлекает вложение из письма и отдает бинарным потоком.

        Args:
            request (HttpRequest): Запрос.
            folder (str): Имя папки.
            uid (int): Идентификатор сообщения.
            part_index (int): Индекс части MIME.

        Returns:
            HttpResponse: Файл с заголовком Content-Disposition.
        """
        account = self.get_account()
        try:
            with self.get_imap_service(account) as imap_svc:
                result = imap_svc.download_attachment(folder, int(uid), int(part_index))
                if not result:
                    raise Http404("Вложение не найдено.")

                filename, content_type, data = result
                response = HttpResponse(data, content_type=content_type)
                # Кодирование имени файла по RFC 5987
                encoded_filename = quote(filename)
                inline = request.GET.get("inline") == "1"
                disposition = "inline" if inline else "attachment"
                response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{encoded_filename}"
                return response
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка скачивания вложения {uid}/{part_index}: {e}")
            raise Http404(f"Ошибка загрузки файла: {e}")


class MailboxActionAPIView(MailboxBaseMixin, View):
    """AJAX API для быстрых и групповых действий над письмами (удаление, отметка прочитанности, перемещение)."""

    def post(self, request):
        """Выполняет операцию над одним или несколькими письмами.

        Returns:
            JsonResponse: Результат выполнения действия.
        """
        account = self.get_account()
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        action = data.get("action")
        folder = data.get("folder", "INBOX")
        target_folder = data.get("target_folder", "")
        uids = data.get("uids", [])

        if isinstance(uids, (int, str)):
            uids = [int(uids)]
        else:
            uids = [int(u) for u in uids if str(u).isdigit()]

        if not action or not uids:
            return JsonResponse({"success": False, "error": "Не указаны параметры action или uids"}, status=400)

        success_count = 0
        try:
            with self.get_imap_service(account) as imap_svc:
                if action in ("mark_seen", "mark_unseen", "toggle_flag", "delete", "move"):
                    if imap_svc.batch_action(folder, uids, action, target_folder):
                        success_count = len(uids)
                elif action in ("not_spam", "unmark_spam"):
                    for uid in uids:
                        ok, sender_info = imap_svc.unmark_spam(folder, uid)
                        if ok:
                            success_count += 1
                            if sender_info:
                                s_name, s_email = sender_info
                                try:
                                    from mailbox_app.models import MailContact
                                    MailContact.objects.update_or_create(
                                        user=request.user,
                                        email=s_email.lower().strip(),
                                        defaults={
                                            "name": s_name.strip() if s_name else s_email.split("@")[0],
                                            "source": "whitelist",
                                        },
                                    )
                                except Exception as c_err:
                                    logger.debug(f"[Mailbox] Ошибка сохранения контакта в whitelist: {c_err}")

            return JsonResponse({"success": True, "processed": success_count, "action": action})
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка выполнения действия {action}: {e}")
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class MailboxContactsAPIView(LoginRequiredMixin, View):
    """API для поиска контактов сотрудников и внешних адресатов (автодополнение)."""

    def get(self, request):
        """Возвращает список подходящих контактов из базы сотрудников и адресной книги.

        Returns:
            JsonResponse: Список контактов с id, text, email, title.
        """
        q = request.GET.get("q", "").strip()
        results = []
        seen_emails = set()

        # 1. Поиск по сотрудникам компании
        users_qs = DataBaseUser.objects.filter(is_active=True).select_related(
            "user_work_profile", "user_work_profile__job"
        )
        if q:
            from django.db.models import Q
            q_variants = list(dict.fromkeys([q, q.lower(), q.upper(), q.capitalize(), q.title()]))
            user_filter = Q()
            for v in q_variants:
                user_filter |= (
                    Q(last_name__icontains=v)
                    | Q(first_name__icontains=v)
                    | Q(surname__icontains=v)
                    | Q(email__icontains=v)
                    | Q(username__icontains=v)
                )
            users_qs = users_qs.filter(user_filter)

        for u in users_qs[:30]:
            user_email = (u.email or "").strip()
            if not user_email and "@" in u.username:
                user_email = u.username.strip()
            if not user_email or user_email.lower() in seen_emails:
                continue

            full_name = f"{u.last_name} {u.first_name} {u.surname or ''}".strip()
            job_title = (
                u.user_work_profile.job.name
                if hasattr(u, "user_work_profile") and u.user_work_profile and u.user_work_profile.job
                else "Сотрудник"
            )

            seen_emails.add(user_email.lower())
            results.append({
                "id": user_email,
                "email": user_email,
                "name": full_name or u.username,
                "job": job_title,
                "text": f"{full_name} <{user_email}>" if full_name else user_email,
            })

        # 2. Поиск по персональной адресной книге (MailContact)
        if request.user.is_authenticated:
            from django.db.models import Q
            from mailbox_app.models import MailContact
            contacts_qs = MailContact.objects.filter(user=request.user)
            if q:
                q_variants = list(dict.fromkeys([q, q.lower(), q.upper(), q.capitalize(), q.title()]))
                contact_filter = Q()
                for v in q_variants:
                    contact_filter |= (
                        Q(name__icontains=v) | Q(email__icontains=v)
                    )
                contacts_qs = contacts_qs.filter(contact_filter)

            for c in contacts_qs[:30]:
                c_email = (c.email or "").strip()
                if not c_email or c_email.lower() in seen_emails:
                    continue

                seen_emails.add(c_email.lower())
                results.append({
                    "id": c_email,
                    "email": c_email,
                    "name": c.name or c_email,
                    "job": "Адресная книга",
                    "text": f"{c.name} <{c_email}>" if c.name else c_email,
                })

        return JsonResponse({"results": results})


class MailboxUnreadCountAPIView(LoginRequiredMixin, View):
    """Легковесный AJAX эндпоинт для проверки непрочитанных входящих писем и пуш-уведомлений."""

    def get(self, request):
        """Возвращает статус непрочитанных писем и данные последнего письма.

        Returns:
            JsonResponse: Словарь с количеством непрочитанных и данными последнего письма.
        """
        account = get_user_mail_account(request.user)
        if not account or not account.email or not account.get_password():
            return JsonResponse({"success": False, "unread_count": 0, "has_new": False})

        email_clean = account.email.strip().lower()
        cache_key = f"mailbox_unread_status_{email_clean}"
        cached_status = cache.get(cache_key)
        if cached_status is not None:
            return JsonResponse(cached_status)

        try:
            with ImapMailService(
                host=account.imap_host,
                port=account.imap_port,
                email_addr=account.email,
                password=account.get_password(),
                use_ssl=account.imap_use_ssl,
            ) as imap_svc:
                # 1. Быстрая проверка количества UNSEEN через команду STATUS
                status_res, status_data = imap_svc.client.status('"INBOX"', "(UNSEEN)")
                unseen_count = 0
                if status_res == "OK" and status_data:
                    stat_line = status_data[0].decode("latin-1")
                    m = re.search(r"UNSEEN\s+(\d+)", stat_line)
                    if m:
                        unseen_count = int(m.group(1))

                latest_mail = None
                if unseen_count > 0:
                    # 2. Если есть непрочитанные, извлекаем заголовок последнего письма
                    imap_svc.client.select('"INBOX"', readonly=True)
                    s_status, s_data = imap_svc.client.search(None, "UNSEEN")
                    if s_status == "OK" and s_data and s_data[0]:
                        uids = s_data[0].split()
                        if uids:
                            last_num = uids[-1]
                            f_status, f_data = imap_svc.client.fetch(
                                last_num, "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
                            )
                            if f_status == "OK" and f_data:
                                raw_uid = None
                                raw_hdr = b""
                                for item in f_data:
                                    if isinstance(item, tuple):
                                        raw_hdr = item[1]
                                        m_uid = re.search(rb"UID\s+(\d+)", item[0])
                                        if m_uid:
                                            raw_uid = int(m_uid.group(1))

                                msg_obj = email.message_from_bytes(raw_hdr)
                                from_val = imap_svc._decode_header_str(msg_obj.get("From", ""))
                                from_name, from_email = parseaddr(from_val)
                                from_name = from_name or from_email or "Новый отправитель"
                                subj_val = imap_svc._decode_header_str(msg_obj.get("Subject", "Без темы"))

                                latest_mail = {
                                    "uid": raw_uid,
                                    "from_name": from_name,
                                    "from_email": from_email,
                                    "subject": subj_val,
                                    "url": reverse("mailbox_app:email_detail", kwargs={"folder": "INBOX", "uid": raw_uid}) if raw_uid else reverse("mailbox_app:index"),
                                }

                res_data = {
                    "success": True,
                    "unread_count": unseen_count,
                    "has_new": unseen_count > 0,
                    "latest": latest_mail,
                }
                cache.set(cache_key, res_data, timeout=20)
                return JsonResponse(res_data)
        except Exception as e:
            logger.debug(f"[Mailbox] Ошибка проверки непрочитанных писем: {e}")
            return JsonResponse({"success": False, "unread_count": 0, "has_new": False, "error": str(e)})


class MailboxSettingsView(MailboxBaseMixin, FormView):
    """Представление для редактирования настроек почты и подписи пользователя."""

    template_name = "mailbox_app/settings.html"
    form_class = MailAccountSettingsForm

    def get_form_kwargs(self):
        """Передает текущий инстанс MailAccount и права суперадминистратора в форму.

        Returns:
            dict: Параметры формы.
        """
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_account()
        kwargs["is_superuser"] = bool(self.request.user.is_superuser)
        return kwargs

    def get_context_data(self, **kwargs):
        """Формирует контекст данных для страницы настроек почты.

        Returns:
            dict: Контекст шаблона с учетной записью и списком папок.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folders = []
        try:
            with self.get_imap_service(account) as imap_svc:
                folders = imap_svc.get_folders()
        except Exception as e:
            logger.debug(f"[Mailbox] Ошибка загрузки папок в настройках: {e}")

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {"name": "Корпоративная почта", "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"})},
                {"name": "Настройки"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": "settings",
        })
        return context

    def form_valid(self, form):
        """Сохраняет обновленные настройки почты.

        Returns:
            HttpResponse: Редирект с уведомлением.
        """
        form.save()
        invalidate_mailbox_cache(self.get_account().email)
        messages.success(self.request, "Настройки почтового ящика успешно сохранены!")
        return redirect("mailbox_app:settings")


class MailboxDiagnosticView(UserPassesTestMixin, MailboxBaseMixin, TemplateView):
    """Представление для детального пошагового профилирования и диагностики почтового сервера.

    Доступно исключительно персоналу (staff) и суперпользователям (superuser).
    """

    template_name = "mailbox_app/diagnostic.html"

    def test_func(self) -> bool:
        """Проверяет права доступа к странице диагностики скорости.

        Returns:
            bool: True, если пользователь является персоналом (staff) или суперадминистратором.
        """
        return bool(
            self.request.user.is_authenticated
            and (self.request.user.is_staff or self.request.user.is_superuser)
        )

    def get_context_data(self, **kwargs):
        """Выполняет серию пошаговых тестов скорости сетевого взаимодействия и команд Kerio Connect.

        Returns:
            dict: Контекст шаблона с хронометражем операций и JSON-отчетом.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        email_addr = account.email if account else ""
        password = account.get_password() if account else ""
        host = account.imap_host if account else "192.168.10.242"
        port = account.imap_port if account else 993
        use_ssl = account.imap_use_ssl if account else True

        steps = []
        error_message = None

        def record(step_name: str, duration_ms: float, details: str = "", status: str = "OK"):
            steps.append({
                "step": step_name,
                "ms": round(duration_ms, 2),
                "details": details,
                "status": status,
            })

        total_start = time.perf_counter()

        if not email_addr or not password:
            error_message = "Почтовый аккаунт или пароль не настроены для текущего пользователя."
        else:
            # 1. DNS Resolution
            t0 = time.perf_counter()
            ip_address = host
            try:
                ip_address = socket.gethostbyname(host)
                dns_ms = (time.perf_counter() - t0) * 1000
                record("1. DNS Resolution (Резолв хоста)", dns_ms, f"IP: {ip_address}")
            except Exception as e:
                dns_ms = (time.perf_counter() - t0) * 1000
                record("1. DNS Resolution (Резолв хоста)", dns_ms, f"Ошибка: {e}", status="ERR")

            # 2. TCP Socket Connect
            t0 = time.perf_counter()
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=5)
                tcp_ms = (time.perf_counter() - t0) * 1000
                record("2. TCP Socket Connect (Сетевой пинг/коннект)", tcp_ms, f"Подключено к {ip_address}:{port}")
            except Exception as e:
                tcp_ms = (time.perf_counter() - t0) * 1000
                record("2. TCP Socket Connect (Сетевой пинг/коннект)", tcp_ms, f"Ошибка TCP: {e}", status="ERR")
                error_message = f"Не удалось установить TCP-соединение с {host}:{port}: {e}"
            finally:
                if sock:
                    sock.close()

            # 2.1 Тест порта 143 (Plain IMAP в локальной сети)
            try:
                t0 = time.perf_counter()
                p_sock = socket.create_connection((host, 143), timeout=3)
                p_conn_ms = (time.perf_counter() - t0) * 1000
                t0 = time.perf_counter()
                p_banner = p_sock.recv(1024).decode("latin-1", errors="ignore").strip()
                p_banner_ms = (time.perf_counter() - t0) * 1000
                p_sock.close()
                record("2.1 Тест порта 143 (Plain IMAP)", p_conn_ms + p_banner_ms, f"Коннект: {p_conn_ms:.1f}мс, Баннер: {p_banner_ms:.1f}мс ({p_banner[:40]})")
            except Exception as e:
                record("2.1 Тест порта 143 (Plain IMAP)", 0.0, f"Порт 143 закрыт или недоступен ({e})", status="INFO")

            # 3. IMAP Connect + SSL Handshake
            if not error_message:
                ssl_ctx = ssl.create_default_context()
                if host.strip().replace(".", "").isdigit():
                    ssl_ctx.check_hostname = False
                    ssl_ctx.verify_mode = ssl.CERT_NONE

                # 3a. Замер чистого SSL Handshake
                try:
                    t0 = time.perf_counter()
                    raw_s = socket.create_connection((host, port), timeout=5)
                    ssl_s = ssl_ctx.wrap_socket(raw_s, server_hostname=None if host.strip().replace(".", "").isdigit() else host)
                    pure_ssl_ms = (time.perf_counter() - t0) * 1000
                    
                    # 3b. Ожидание приветственного баннера от сервера
                    t0 = time.perf_counter()
                    server_banner = ssl_s.recv(1024).decode("latin-1", errors="ignore").strip()
                    banner_ms = (time.perf_counter() - t0) * 1000
                    ssl_s.close()
                    
                    record("3a. Чистый SSL Handshake (TLS crypto)", pure_ssl_ms, f"Шифр: {ssl_s.cipher()[0] if hasattr(ssl_s, 'cipher') else 'TLS'}")
                    record("3b. Ожидание баннера сервера (Reverse DNS/Kerio)", banner_ms, f"Баннер: {server_banner[:60]}")
                except Exception as e:
                    record("3a. Проверка сокета SSL", 0.0, f"Ошибка: {e}", status="WARN")

                client = None
                t0 = time.perf_counter()
                try:
                    if use_ssl:
                        client = imaplib.IMAP4_SSL(host, port, ssl_context=ssl_ctx)
                    else:
                        client = imaplib.IMAP4(host, port)
                    ssl_ms = (time.perf_counter() - t0) * 1000
                    cipher_info = ""
                    if use_ssl and hasattr(client, "ssl") and client.ssl:
                        cipher_info = f"Cipher: {client.ssl.cipher()[0]}, TLS: {client.ssl.version()}"
                    record("3. Полная инициализация IMAP4_SSL", ssl_ms, cipher_info)
                except Exception as e:
                    ssl_ms = (time.perf_counter() - t0) * 1000
                    record("3. Полная инициализация IMAP4_SSL", ssl_ms, f"Ошибка SSL: {e}", status="ERR")
                    error_message = f"Ошибка SSL-рукопожатия: {e}"

                # 4. IMAP Login
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        login_status, login_res = client.login(email_addr, password)
                        login_ms = (time.perf_counter() - t0) * 1000
                        record("4. IMAP Login (Авторизация)", login_ms, f"Ответ сервера: {login_status}")
                    except Exception as e:
                        login_ms = (time.perf_counter() - t0) * 1000
                        record("4. IMAP Login (Авторизация)", login_ms, f"Ошибка входа: {e}", status="ERR")
                        error_message = f"Ошибка авторизации IMAP: {e}"

                # 5. IMAP Capability
                if client and not error_message:
                    try:
                        caps_status, caps_data = client.capability()
                        caps_str = caps_data[0].decode("latin-1") if caps_data and caps_data[0] else ""
                        record("5. IMAP CAPABILITY (Возможности сервера)", 0.1, f"EXT: {caps_str[:60]}...")
                    except Exception:
                        pass

                # 6. IMAP LIST Folders
                folder_count = 0
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        status, folder_list = client.list()
                        list_ms = (time.perf_counter() - t0) * 1000
                        if folder_list:
                            folder_count = len([f for f in folder_list if f])
                        record("6. IMAP LIST (Получение списка папок)", list_ms, f"Папок: {folder_count}")
                    except Exception as e:
                        list_ms = (time.perf_counter() - t0) * 1000
                        record("6. IMAP LIST (Получение списка папок)", list_ms, f"Ошибка: {e}", status="ERR")

                # 7. IMAP SELECT INBOX
                inbox_msgs = 0
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        status, select_data = client.select('"INBOX"', readonly=True)
                        select_ms = (time.perf_counter() - t0) * 1000
                        if select_data and select_data[0]:
                            inbox_msgs = int(select_data[0].decode("ascii", errors="ignore") or 0)
                        record("7. IMAP SELECT 'INBOX' (Открытие папки)", select_ms, f"Сообщений в INBOX: {inbox_msgs}")
                    except Exception as e:
                        select_ms = (time.perf_counter() - t0) * 1000
                        record("7. IMAP SELECT 'INBOX' (Открытие папки)", select_ms, f"Ошибка: {e}", status="ERR")

                # 8. IMAP UID SEARCH ALL
                uids = []
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        status, search_data = client.uid("search", None, "ALL")
                        search_ms = (time.perf_counter() - t0) * 1000
                        if search_data and search_data[0]:
                            uids = [u for u in search_data[0].split() if u and u != b"0"]
                        record("8. IMAP UID SEARCH ALL (Поиск всех UIDs)", search_ms, f"Всего писем: {len(uids)}")
                    except Exception as e:
                        search_ms = (time.perf_counter() - t0) * 1000
                        record("8. IMAP UID SEARCH ALL (Поиск всех UIDs)", search_ms, f"Ошибка: {e}", status="ERR")

                # 8b. IMAP UID SORT (REVERSE DATE)
                sorted_uids = []
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        status, sort_data = client.uid("sort", "(REVERSE DATE)", "UTF-8", "ALL")
                        sort_ms = (time.perf_counter() - t0) * 1000
                        if sort_data and sort_data[0]:
                            sorted_uids = [u for u in sort_data[0].split() if u and u != b"0"]
                        record("8b. IMAP UID SORT (REVERSE DATE)", sort_ms, f"Отсортировано по реальной дате: {len(sorted_uids)}")
                    except Exception as e:
                        sort_ms = (time.perf_counter() - t0) * 1000
                        record("8b. IMAP UID SORT (REVERSE DATE)", sort_ms, f"Ошибка/Fallback: {e}", status="WARN")

                # 9. IMAP UID SEARCH UNSEEN
                unseen_uids = []
                if client and not error_message:
                    t0 = time.perf_counter()
                    try:
                        status, unseen_data = client.uid("search", None, "UNSEEN")
                        unseen_ms = (time.perf_counter() - t0) * 1000
                        if unseen_data and unseen_data[0]:
                            unseen_uids = [u for u in unseen_data[0].split() if u and u != b"0"]
                        record("9. IMAP UID SEARCH UNSEEN (Непрочитанные)", unseen_ms, f"Непрочитанных: {len(unseen_uids)}")
                    except Exception as e:
                        unseen_ms = (time.perf_counter() - t0) * 1000
                        record("9. IMAP UID SEARCH UNSEEN (Непрочитанные)", unseen_ms, f"Ошибка: {e}", status="ERR")

                # 10. IMAP Batch FETCH 25
                batch_uids = uids[-25:] if len(uids) >= 25 else uids
                batch_bytes = 0
                fetch_data = None
                if client and not error_message and batch_uids:
                    batch_uids_rev = list(reversed(batch_uids))
                    uids_seq = ",".join(u.decode("ascii") if isinstance(u, bytes) else str(u) for u in batch_uids_rev)
                    t0 = time.perf_counter()
                    try:
                        status, fetch_data = client.uid(
                            "fetch",
                            uids_seq,
                            "(FLAGS INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE MESSAGE-ID CONTENT-TYPE)])"
                        )
                        fetch_ms = (time.perf_counter() - t0) * 1000
                        if fetch_data:
                            for item in fetch_data:
                                if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                                    batch_bytes += len(item[1])
                        record("10. IMAP Batch FETCH (25 заголовков)", fetch_ms, f"Объем данных: {batch_bytes / 1024:.1f} KB")
                    except Exception as e:
                        fetch_ms = (time.perf_counter() - t0) * 1000
                        record("10. IMAP Batch FETCH (25 заголовков)", fetch_ms, f"Ошибка FETCH: {e}", status="ERR")

                # 11. Python Parsing of 25 headers
                if fetch_data:
                    t0 = time.perf_counter()
                    parsed_count = 0
                    for item in fetch_data:
                        if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], bytes):
                            msg = email.message_from_bytes(item[1])
                            _subj = msg.get("Subject") or ""
                            _fn, _fe = parseaddr(msg.get("From") or "")
                            parsed_count += 1
                    parse_ms = (time.perf_counter() - t0) * 1000
                    record("11. Python Parsing (Парсинг 25 писем)", parse_ms, f"Обработано сообщений: {parsed_count}")

                # 12. IMAP Logout
                if client:
                    t0 = time.perf_counter()
                    try:
                        client.logout()
                        logout_ms = (time.perf_counter() - t0) * 1000
                        record("12. IMAP Logout / Закрытие сессии", logout_ms, "Соединение корректно закрыто")
                    except Exception:
                        pass

        total_time_ms = (time.perf_counter() - total_start) * 1000

        diag_report = {
            "target": f"{host}:{port}",
            "ssl": use_ssl,
            "account": email_addr,
            "total_ms": round(total_time_ms, 2),
            "steps": steps,
            "error": error_message,
        }
        json_report_str = json.dumps(diag_report, ensure_ascii=False, indent=2)

        context.update({
            "email_addr": email_addr,
            "host": host,
            "port": port,
            "use_ssl": use_ssl,
            "steps": steps,
            "total_time_ms": total_time_ms,
            "total_time_sec": total_time_ms / 1000.0,
            "error_message": error_message,
            "json_report": json_report_str,
        })
        return context


class MailboxScheduledListView(MailboxBaseMixin, ListView):
    """Представление для просмотра и управления письмами, запланированными к отправке."""

    template_name = "mailbox_app/scheduled_list.html"
    context_object_name = "scheduled_emails"
    paginate_by = 25

    def get_queryset(self):
        """Возвращает запланированные письма текущего пользователя с фильтрацией по статусу.

        Returns:
            QuerySet[ScheduledEmail]: Запланированные письма пользователя.
        """
        status_filter = self.request.GET.get("status", "")
        qs = (
            ScheduledEmail.objects.filter(user=self.request.user)
            .select_related("account")
            .prefetch_related("attachments")
        )
        if status_filter in dict(ScheduledEmail.STATUS_CHOICES):
            qs = qs.filter(status=status_filter)

        if status_filter in ("sent", "cancelled", "failed"):
            return qs.order_by("-scheduled_at")
        elif status_filter == "pending":
            return qs.order_by("scheduled_at")
        else:
            from django.db.models import Case, When, Value, IntegerField
            return qs.annotate(
                status_priority=Case(
                    When(status=ScheduledEmail.STATUS_PENDING, then=Value(1)),
                    When(status=ScheduledEmail.STATUS_PROCESSING, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            ).order_by("status_priority", "scheduled_at", "-created_at")

    def get_context_data(self, **kwargs):
        """Формирует контекст шаблона для страницы запланированных писем.

        Returns:
            dict: Данные контекста шаблона.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folders = []
        if account:
            try:
                with self.get_imap_service(account) as imap_svc:
                    folders = imap_svc.get_folders()
            except Exception:
                pass

        status_filter = self.request.GET.get("status", "")
        counts = {
            "all": ScheduledEmail.objects.filter(user=self.request.user).count(),
            "pending": ScheduledEmail.objects.filter(
                user=self.request.user, status=ScheduledEmail.STATUS_PENDING
            ).count(),
            "sent": ScheduledEmail.objects.filter(
                user=self.request.user, status=ScheduledEmail.STATUS_SENT
            ).count(),
            "failed": ScheduledEmail.objects.filter(
                user=self.request.user, status=ScheduledEmail.STATUS_FAILED
            ).count(),
            "cancelled": ScheduledEmail.objects.filter(
                user=self.request.user, status=ScheduledEmail.STATUS_CANCELLED
            ).count(),
        }

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {
                    "name": "Корпоративная почта",
                    "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"}),
                },
                {"name": "Запланированные письма"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": "scheduled",
            "current_folder_display": "Запланированные",
            "scheduled_count": self.get_scheduled_count(),
            "status_filter": status_filter,
            "status_counts": counts,
            "status_choices": ScheduledEmail.STATUS_CHOICES,
        })
        return context


class MailboxScheduledActionAPIView(MailboxBaseMixin, View):
    """AJAX API контроллер для управления отложенными письмами."""

    def post(self, request, *args, **kwargs):
        """Обрабатывает запросы на отмену, отправку сейчас или перенос письма.

        Args:
            request (HttpRequest): Запрос с параметрами действия.

        Returns:
            JsonResponse: Результат выполнения операции в формате JSON.
        """
        import json
        from django.http import JsonResponse
        from django.utils.dateparse import parse_datetime
        from mailbox_app.services.scheduled_mail_service import (
            cancel_scheduled_email,
            reschedule_email,
            send_single_scheduled_email,
        )

        try:
            if request.content_type == "application/json":
                data = json.loads(request.body.decode("utf-8"))
            else:
                data = request.POST

            action = data.get("action")
            email_id_raw = data.get("email_id")
            if not email_id_raw or not action:
                return JsonResponse(
                    {"success": False, "error": "Некорректные параметры запроса."},
                    status=400,
                )

            email_id = int(email_id_raw)

            if action == "cancel":
                cancel_scheduled_email(email_id, request.user)
                return JsonResponse(
                    {"success": True, "message": "Отправка письма успешно отменена."}
                )

            elif action == "send_now":
                from mailbox_app.tasks import send_scheduled_email_task

                try:
                    send_single_scheduled_email(email_id)
                    return JsonResponse(
                        {"success": True, "message": "Письмо успешно отправлено!"}
                    )
                except Exception as e:
                    logger.warning(
                        f"[Mailbox] Прямая отправка не удалась, ставим в Celery: {e}"
                    )
                    send_scheduled_email_task.delay(email_id)
                    return JsonResponse(
                        {"success": True, "message": "Письмо поставлено в очередь на отправку."}
                    )

            elif action == "reschedule":
                new_dt_raw = data.get("new_scheduled_at", "")
                if not new_dt_raw:
                    return JsonResponse(
                        {"success": False, "error": "Не указана новая дата отправки."},
                        status=400,
                    )
                new_dt = parse_datetime(new_dt_raw)
                if not new_dt:
                    return JsonResponse(
                        {"success": False, "error": "Неверный формат даты и времени."},
                        status=400,
                    )
                if timezone.is_naive(new_dt):
                    new_dt = timezone.make_aware(new_dt, timezone.get_current_timezone())
                reschedule_email(email_id, new_dt, request.user)
                return JsonResponse({
                    "success": True,
                    "message": f"Время отправки изменено на {new_dt:%d.%m.%Y %H:%M} (МСК).",
                })

            elif action == "delete":
                scheduled_email = ScheduledEmail.objects.get(id=email_id)
                if scheduled_email.user != request.user and not request.user.is_superuser:
                    return JsonResponse(
                        {"success": False, "error": "Доступ запрещен."},
                        status=403,
                    )
                if scheduled_email.status == ScheduledEmail.STATUS_PROCESSING:
                    return JsonResponse(
                        {"success": False, "error": "Нельзя удалить письмо в процессе отправки."},
                        status=400,
                    )
                scheduled_email.delete()
                return JsonResponse(
                    {"success": True, "message": "Запись успешно удалена."}
                )

            return JsonResponse(
                {"success": False, "error": f"Неизвестное действие '{action}'."},
                status=400,
            )

        except Exception as err:
            logger.error(f"[Mailbox] Ошибка в MailboxScheduledActionAPIView: {err}", exc_info=True)
            return JsonResponse({"success": False, "error": str(err)}, status=400)


class MailboxScheduledDetailView(MailboxBaseMixin, DetailView):
    """Представление для детального просмотра параметров и содержимого отложенного письма."""

    model = ScheduledEmail
    template_name = "mailbox_app/scheduled_detail.html"
    context_object_name = "scheduled_email"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        """Ограничивает выборку только письмами текущего пользователя или администратора.

        Returns:
            QuerySet[ScheduledEmail]: Запрос отложенных писем с предзагрузкой связей.
        """
        qs = (
            ScheduledEmail.objects.select_related("account", "user")
            .prefetch_related("attachments")
        )
        if not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        """Формирует контекст детального просмотра запланированного письма.

        Returns:
            dict: Словарь с данными для шаблона.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folders = []
        if account:
            try:
                with self.get_imap_service(account) as imap_svc:
                    folders = imap_svc.get_folders()
            except Exception:
                pass

        obj = self.get_object()
        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {
                    "name": "Корпоративная почта",
                    "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"}),
                },
                {
                    "name": "Запланированные письма",
                    "url": reverse("mailbox_app:scheduled_list"),
                },
                {"name": obj.subject or "(Без темы)"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": "scheduled",
            "current_folder_display": "Запланированные",
            "scheduled_count": self.get_scheduled_count(),
            "can_edit": obj.can_reschedule,
            "can_cancel": obj.can_cancel,
            "can_send_now": obj.can_send_now,
        })
        return context


class MailboxScheduledEditView(MailboxBaseMixin, FormView):
    """Представление для редактирования параметров и текста запланированного письма."""

    form_class = ScheduledEmailEditForm
    template_name = "mailbox_app/scheduled_edit.html"

    def dispatch(self, request, *args, **kwargs):
        """Проверяет права доступа и допустимость редактирования письма.

        Args:
            request (HttpRequest): Текущий HTTP-запрос.

        Returns:
            HttpResponse: Ответ сервера.
        """
        self.scheduled_email = self.get_scheduled_email()
        if not self.scheduled_email.can_reschedule:
            messages.warning(
                request,
                f"Письмо в статусе «{self.scheduled_email.get_status_display()}» нельзя редактировать.",
            )
            return redirect("mailbox_app:scheduled_detail", pk=self.scheduled_email.id)
        return super().dispatch(request, *args, **kwargs)

    def get_scheduled_email(self) -> ScheduledEmail:
        """Получает объект запланированного письма с проверкой прав.

        Returns:
            ScheduledEmail: Экземпляр письма.

        Raises:
            Http404: Если письмо не найдено или нет прав доступа.
        """
        pk = self.kwargs.get("pk")
        from mailbox_app.services.scheduled_mail_service import get_scheduled_email_for_user

        try:
            return get_scheduled_email_for_user(pk, self.request.user)
        except Exception:
            raise Http404("Запланированное письмо не найдено.")

    def get_initial(self):
        """Заполняет начальные значения формы данными из существующего письма.

        Returns:
            dict: Начальные данные формы.
        """
        initial = super().get_initial()
        email_obj = self.scheduled_email
        initial.update({
            "to": email_obj.to_recipients,
            "cc": email_obj.cc_recipients,
            "bcc": email_obj.bcc_recipients,
            "subject": email_obj.subject,
            "body_html": email_obj.body_html,
            "scheduled_at": email_obj.scheduled_at,
            "send_mode": "scheduled",
        })
        return initial

    def get_context_data(self, **kwargs):
        """Формирует контекст шаблона редактирования отложенного письма.

        Returns:
            dict: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        account = self.get_account()
        folders = []
        if account:
            try:
                with self.get_imap_service(account) as imap_svc:
                    folders = imap_svc.get_folders()
            except Exception:
                pass

        context.update({
            "title": "КОРПОРАТИВНАЯ ПОЧТА",
            "breadcrumbs": [
                {
                    "name": "Корпоративная почта",
                    "url": reverse("mailbox_app:folder", kwargs={"folder": "INBOX"}),
                },
                {
                    "name": "Запланированные письма",
                    "url": reverse("mailbox_app:scheduled_list"),
                },
                {
                    "name": self.scheduled_email.subject or "(Без темы)",
                    "url": reverse("mailbox_app:scheduled_detail", kwargs={"pk": self.scheduled_email.id}),
                },
                {"name": "Редактирование"},
            ],
            "account": account,
            "folders": folders,
            "current_folder": "scheduled",
            "current_folder_display": "Запланированные",
            "scheduled_count": self.get_scheduled_count(),
            "scheduled_email": self.scheduled_email,
            "existing_attachments": self.scheduled_email.attachments.all(),
        })
        return context

    def form_valid(self, form):
        """Сохраняет обновленные данные запланированного письма или отправляет его немедленно.

        Args:
            form (ScheduledEmailEditForm): Валидированная форма.

        Returns:
            HttpResponse: Редирект на детальный просмотр или в реестр.
        """
        from mailbox_app.services.scheduled_mail_service import (
            send_single_scheduled_email,
            update_scheduled_email,
        )

        send_mode = form.cleaned_data.get("send_mode") or "scheduled"
        scheduled_at = form.cleaned_data.get("scheduled_at") or self.scheduled_email.scheduled_at
        new_files = self.request.FILES.getlist("attachments")

        # Проверяем, какие из старых вложений были отмечены для удаления
        delete_ids_raw = self.request.POST.getlist("delete_attachment_ids")
        delete_ids = [int(i) for i in delete_ids_raw if i.isdigit()]

        try:
            updated_email = update_scheduled_email(
                scheduled_email_id=self.scheduled_email.id,
                user=self.request.user,
                to_recipients=form.cleaned_data["to"],
                subject=form.cleaned_data.get("subject", "(Без темы)"),
                body_html=form.cleaned_data.get("body_html", ""),
                scheduled_at=scheduled_at,
                cc_recipients=form.cleaned_data.get("cc", ""),
                bcc_recipients=form.cleaned_data.get("bcc", ""),
                new_files=new_files,
                delete_attachment_ids=delete_ids,
            )

            # Если пользователь нажал "Отправить сейчас"
            if send_mode == "now":
                try:
                    send_single_scheduled_email(updated_email.id)
                    messages.success(self.request, "Письмо успешно отправлено адресатам!")
                    return redirect("mailbox_app:scheduled_list")
                except Exception as e:
                    from mailbox_app.tasks import send_scheduled_email_task

                    logger.warning(f"[Mailbox] Ошибка немедленной отправки: {e}, ставим в очередь Celery")
                    send_scheduled_email_task.delay(updated_email.id)
                    messages.info(self.request, "Письмо сохранено и поставлено в очередь отправки Celery.")
                    return redirect("mailbox_app:scheduled_detail", pk=updated_email.id)

            messages.success(
                self.request,
                f"Запланированное письмо успешно обновлено! Отправка запланирована на {scheduled_at:%d.%m.%Y %H:%M} (МСК).",
            )
            return redirect("mailbox_app:scheduled_detail", pk=updated_email.id)

        except Exception as err:
            logger.error(f"[Mailbox] Ошибка обновления отложенного письма: {err}", exc_info=True)
            messages.error(self.request, f"Ошибка при сохранении изменений: {err}")
            return self.form_invalid(form)


class MailboxScheduledAttachmentDownloadView(MailboxBaseMixin, View):
    """Контроллер для безопасного скачивания файла-вложения запланированного письма."""

    def get(self, request, pk: int, att_id: int, *args, **kwargs):
        """Отдает бинарный файл вложения с проверкой прав доступа.

        Args:
            request (HttpRequest): Запрос пользователя.
            pk (int): ID запланированного письма.
            att_id (int): ID файла-вложения.

        Returns:
            FileResponse: Ответ с файлом для скачивания или просмотра.

        Raises:
            Http404: Если файл или письмо не найдены.
        """
        from mailbox_app.services.scheduled_mail_service import get_scheduled_email_for_user

        try:
            scheduled_email = get_scheduled_email_for_user(pk, request.user)
            attachment = scheduled_email.attachments.get(id=att_id)
            if not attachment.file or not attachment.file.storage.exists(attachment.file.name):
                raise Http404("Файл не найден на диске сервера.")

            response = FileResponse(
                attachment.file.open("rb"),
                content_type=attachment.content_type or "application/octet-stream",
            )
            safe_filename = quote(attachment.filename)
            response["Content-Disposition"] = f"inline; filename*=UTF-8''{safe_filename}"
            return response
        except Exception as e:
            logger.warning(f"[Mailbox] Ошибка отдачи вложения отложенного письма: {e}")
            raise Http404("Вложение не найдено.")





