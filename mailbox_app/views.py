"""Представления (Views) приложения корпоративной веб-почты."""

import html
import json
import logging
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, TemplateView

from customers_app.models import DataBaseUser
from mailbox_app.forms import MailAccountSettingsForm, MailComposeForm
from mailbox_app.models import MailAccount
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

    def get_account(self) -> MailAccount:
        """Возвращает или настраивает почтовый аккаунт для текущего пользователя.

        Returns:
            MailAccount: Объект почтового ящика.

        Raises:
            Http404: Если у пользователя не настроена почта.
        """
        account = get_user_mail_account(self.request.user)
        if not account or not account.email:
            raise Http404("Корпоративный почтовый ящик не настроен для данного пользователя.")
        return account

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
        sort_by = self.request.GET.get("sort", "date").strip().lower()
        sort_dir = self.request.GET.get("dir", "desc").strip().lower()
        filter_by = self.request.GET.get("filter", "all").strip().lower()
        page = int(self.request.GET.get("page", 1))
        per_page = 25

        folders = []
        email_messages = []
        total_count = 0
        error_message = None

        try:
            with self.get_imap_service(account) as imap_svc:
                folders = imap_svc.get_folders()
                email_messages, total_count = imap_svc.get_messages(
                    folder_name=current_folder,
                    page=page,
                    per_page=per_page,
                    query=search_query if search_query else None,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    filter_by=filter_by,
                )
        except Exception as e:
            logger.error(f"[Mailbox] Ошибка загрузки писем из {current_folder}: {e}")
            error_message = f"Не удалось подключиться к серверу IMAP: {e}"

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        current_type = "custom"
        current_folder_display = decode_imap_utf7(current_folder)
        for f in folders:
            if f.get("raw_name") == current_folder:
                current_type = f.get("type", "custom")
                current_folder_display = f.get("display_name", current_folder_display)
                break
        is_junk = current_type in ("junk", "spam") or any(s in current_folder.lower() for s in ("junk", "спам", "spam"))

        sort_labels = {
            ("date", "desc"): "По дате (сначала новые)",
            ("date", "asc"): "По дате (сначала старые)",
            ("from", "asc"): "По автору (А → Я)",
            ("from", "desc"): "По автору (Я → А)",
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
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "filter_by": filter_by,
            "current_sort_label": current_sort_label,
            "query_prefix": query_prefix,
            "messages_list": email_messages,
            "total_count": total_count,
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
            "search_query": search_query,
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
                folders = imap_svc.get_folders()
                email_data = imap_svc.get_message_detail(folder_name, uid)
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
                current_folder_display = f.get("display_name", current_folder_display)
                break
        is_junk = current_type in ("junk", "spam") or any(s in folder_name.lower() for s in ("junk", "спам", "spam"))

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
        """Добавляет список папок в контекст формы написания письма.

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
        })
        return context

    def form_valid(self, form):
        """Обрабатывает отправку письма через SMTP-сервер.

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


class MailboxAttachmentDownloadView(MailboxBaseMixin, View):
    """Представление для безопасного скачивания файла-вложения."""

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
    """AJAX API для быстрых действий над письмами (удаление, отметка прочитанности, звездочка)."""

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
                for uid in uids:
                    if action == "mark_seen":
                        if imap_svc.mark_seen(folder, uid, is_seen=True):
                            success_count += 1
                    elif action == "mark_unseen":
                        if imap_svc.mark_seen(folder, uid, is_seen=False):
                            success_count += 1
                    elif action == "toggle_flag":
                        if imap_svc.toggle_flag(folder, uid, "\\Flagged"):
                            success_count += 1
                    elif action == "delete":
                        if imap_svc.delete_message(folder, uid):
                            success_count += 1
                    elif action in ("not_spam", "unmark_spam"):
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


class MailboxSettingsView(MailboxBaseMixin, FormView):
    """Представление для редактирования настроек почты и подписи пользователя."""

    template_name = "mailbox_app/settings.html"
    form_class = MailAccountSettingsForm

    def get_form_kwargs(self):
        """Передает текущий инстанс MailAccount в форму.

        Returns:
            dict: Параметры формы.
        """
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_account()
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


