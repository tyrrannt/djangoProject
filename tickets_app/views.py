"""Контроллеры и представления модуля заявок и добровольных сообщений (tickets_app.views).

Реализует:
- Просмотр реестра заявок с KPI-сводкой для руководства;
- Детальный просмотр заявки и ветки обсуждения с разграничением служебных заметок;
- Создание и редактирование заявок;
- Добавление сообщений и вложений с асинхронными Celery-уведомлениями.
"""

import logging
from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from customers_app.models import DataBaseUser
from .forms import MessageForm, TicketCreateForm, TicketUpdateForm
from .models import Message, Ticket, TicketSettings, TicketStatus
from .services import (
    can_manage_curator,
    is_ticket_manager,
    save_ticket_attachments,
    send_ticket_notification_async,
)

logger = logging.getLogger(__name__)


class TicketListView(LoginRequiredMixin, ListView):
    """Реестр добровольных сообщений и заявок.

    - Обычный заявитель видит только свои сообщения;
    - Назначенный специалист видит порученные ему заявки;
    - Руководство, администраторы и назначенный куратор СДС видят сквозной реестр компании с KPI-сводкой.
    """

    model = Ticket
    template_name = 'tickets_app/ticket_list.html'
    context_object_name = 'tickets'

    def get_queryset(self):
        """Формирует оптимизированный QuerySet с аннотацией количества обжалований."""
        user = self.request.user
        queryset = (
            Ticket.objects.select_related('author', 'responsible', 'parent_ticket')
            .annotate(appeals_count=Count('appeals'))
            .order_by('-created_at')
        )

        is_manager = is_ticket_manager(user)
        if is_manager:
            unassigned = self.request.GET.get('unassigned')
            if unassigned == '1':
                queryset = queryset.filter(responsible__isnull=True, status=TicketStatus.NEW)
            status_filter = self.request.GET.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            return queryset

        return queryset.filter(Q(author=user) | Q(responsible=user)).distinct()

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет достоверные статистические KPI-метрики для руководства и куратора."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_manager = is_ticket_manager(user)
        can_assign = can_manage_curator(user)

        if is_manager:
            context['total_count'] = Ticket.objects.count()
            context['unassigned_count'] = Ticket.objects.filter(
                responsible__isnull=True,
                status=TicketStatus.NEW,
            ).count()
            context['in_progress_count'] = Ticket.objects.filter(
                status__in=[TicketStatus.IN_PROGRESS, TicketStatus.REDIRECTED],
            ).count()
            context['resolved_count'] = Ticket.objects.filter(
                status__in=[TicketStatus.RESOLVED, TicketStatus.CLOSED],
            ).count()
        else:
            user_tickets = Ticket.objects.filter(Q(author=user) | Q(responsible=user))
            context['total_count'] = user_tickets.count()
            context['unassigned_count'] = user_tickets.filter(
                responsible__isnull=True,
                status=TicketStatus.NEW,
            ).count()
            context['in_progress_count'] = user_tickets.filter(
                status__in=[TicketStatus.IN_PROGRESS, TicketStatus.REDIRECTED],
            ).count()
            context['resolved_count'] = user_tickets.filter(
                status__in=[TicketStatus.RESOLVED, TicketStatus.CLOSED],
            ).count()

        context['is_manager'] = is_manager
        context['curator'] = TicketSettings.get_curator()
        context['can_assign_curator'] = can_assign
        if can_assign:
            context['staff_users'] = (
                DataBaseUser.objects.filter(is_active=True, is_staff=True)
                .select_related('user_work_profile__job')
                .order_by('last_name', 'first_name')
            )
        return context


class TicketDetailView(LoginRequiredMixin, DetailView):
    """Детальный просмотр заявки, материалов расследования и переписки."""

    model = Ticket
    template_name = 'tickets_app/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        """Формирует выборку с предварительной загрузкой связанных сообщений и вложений."""
        user = self.request.user
        is_manager = is_ticket_manager(user)

        messages_qs = (
            Message.objects.select_related('sender')
            .prefetch_related('attachments')
            .order_by('created_at')
        )

        queryset = (
            Ticket.objects.select_related('author', 'responsible', 'parent_ticket')
            .prefetch_related(
                Prefetch('messages', queryset=messages_qs),
                'attachments',
                'appeals',
            )
        )

        if is_manager:
            return queryset
        return queryset.filter(Q(author=user) | Q(responsible=user))

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Фильтрует служебные заметки и готовит форму ответа."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        ticket: Ticket = self.object

        is_manager = is_ticket_manager(user)
        is_responsible = ticket.responsible == user

        # Служебные заметки скрываются от заявителя
        all_messages = list(ticket.messages.all())
        if not is_manager and not is_responsible:
            visible_messages = [m for m in all_messages if not m.is_internal]
        else:
            visible_messages = all_messages

        context['visible_messages'] = visible_messages
        context['visible_messages_count'] = len(visible_messages)
        context['is_manager'] = is_manager
        context['is_responsible'] = is_responsible
        context['can_manage'] = is_manager
        context['can_edit'] = is_manager or (ticket.author == user and not ticket.is_closed_or_resolved)
        context['curator'] = TicketSettings.get_curator()
        context['message_form'] = MessageForm()
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    """Создание нового добровольного сообщения с загрузкой вложений."""

    model = Ticket
    form_class = TicketCreateForm
    template_name = 'tickets_app/ticket_form.html'

    def get_form_kwargs(self) -> Dict[str, Any]:
        """Передает текущего пользователя в форму для фильтрации доступных обжалований."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form: TicketCreateForm) -> HttpResponse:
        """Сохраняет заявку, вложения и инициирует асинхронное Celery-уведомление руководству."""
        form.instance.author = self.request.user
        response = super().form_valid(form)

        # Сохранение прикрепленных файлов с обязательной валидацией расширений
        files = form.cleaned_data.get('attachments')
        if files:
            save_ticket_attachments(files, ticket=self.object)

        # Асинхронная отправка почтовых уведомлений через Celery
        send_ticket_notification_async(
            event_type='new',
            ticket=self.object,
            request=self.request,
            actor=self.request.user,
        )

        messages.success(self.request, f'Добровольное сообщение #{self.object.pk} успешно зарегистрировано.')
        return response


class TicketUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Редактирование заявки (назначение ответственного, смена статуса, корректировка темы)."""

    model = Ticket
    form_class = TicketUpdateForm
    template_name = 'tickets_app/ticket_form.html'

    def test_func(self) -> bool:
        """Проверяет право пользователя на изменение параметров заявки."""
        ticket: Ticket = self.get_object()
        user = self.request.user
        is_manager = is_ticket_manager(user)
        if not (is_manager or ticket.author == user):
            return False
        if ticket.is_closed_or_resolved and not is_manager:
            return False
        return True

    def get_form_kwargs(self) -> Dict[str, Any]:
        """Передает пользователя в форму для контроля прав изменения статусов."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет признак прав менеджера в контекст формы редактирования."""
        context = super().get_context_data(**kwargs)
        context['is_manager'] = is_ticket_manager(self.request.user)
        return context

    def form_valid(self, form: TicketUpdateForm) -> HttpResponse:
        """Транзакционно сохраняет изменения статуса, фиксирует resolved_at и рассылает уведомления."""
        old_ticket = Ticket.objects.get(pk=self.object.pk)
        old_status = old_ticket.status
        old_responsible = old_ticket.responsible

        # Корректировка даты решения при смене статуса
        new_status = form.cleaned_data.get('status') or form.instance.status
        if new_status == TicketStatus.RESOLVED and old_status != TicketStatus.RESOLVED:
            form.instance.resolved_at = timezone.now()
        elif old_status == TicketStatus.RESOLVED and new_status != TicketStatus.RESOLVED:
            form.instance.resolved_at = None

        response = super().form_valid(form)

        # Уведомление назначенному сотруднику
        if form.instance.responsible and form.instance.responsible != old_responsible:
            send_ticket_notification_async(
                event_type='assigned',
                ticket=form.instance,
                request=self.request,
                actor=self.request.user,
            )
            messages.success(self.request, f'Ответственный специалист назначен: {form.instance.responsible}.')

        # Уведомление заявителю о завершении/решении
        if form.instance.status == TicketStatus.RESOLVED and old_status != TicketStatus.RESOLVED:
            send_ticket_notification_async(
                event_type='resolved',
                ticket=form.instance,
                request=self.request,
                actor=self.request.user,
            )
            messages.success(self.request, 'Заявка успешно переведена в статус «Решено».')

        return response


def add_message_to_ticket(request: HttpRequest, pk: int) -> HttpResponse:
    """Добавляет новое сообщение или отчет о принятых мерах в переписку по заявке.

    Args:
        request (HttpRequest): Объект HTTP-запроса.
        pk (int): Идентификатор заявки.

    Returns:
        HttpResponse: Перенаправление на страницу детального просмотра заявки.
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    is_manager = is_ticket_manager(request.user)
    is_author = ticket.author == request.user
    is_responsible = ticket.responsible == request.user

    if not (is_manager or is_author or is_responsible):
        messages.error(request, 'У вас нет доступа к данному добровольному сообщению.')
        return redirect('tickets_app:list')

    if ticket.is_closed_or_resolved:
        messages.error(request, 'Нельзя добавлять сообщения в закрытую или решенную заявку.')
        return redirect('tickets_app:detail', pk=ticket.pk)

    if request.method == 'POST':
        message_form = MessageForm(request.POST, request.FILES)
        if message_form.is_valid():
            message_obj: Message = message_form.save(commit=False)
            message_obj.ticket = ticket
            message_obj.sender = request.user

            # Обычные заявители не могут создавать скрытые служебные заметки
            if not is_manager and not is_responsible:
                message_obj.is_internal = False

            message_obj.save()

            # Сохранение вложений через валидирующий сервис
            files = message_form.cleaned_data.get('attachments')
            if files:
                save_ticket_attachments(files, message=message_obj)

            # Корректная логика смены статуса заявки при ответе
            new_status = request.POST.get('status')
            valid_statuses = [s[0] for s in TicketStatus.choices]

            if new_status and new_status in valid_statuses and not is_author and new_status != ticket.status:
                ticket.status = new_status
                if new_status == TicketStatus.RESOLVED:
                    ticket.resolved_at = timezone.now()
                else:
                    ticket.resolved_at = None
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])

            elif ticket.status == TicketStatus.NEW and (is_manager or is_responsible) and not is_author:
                # Автоматический перевод в работу при первом официальном ответе специалиста
                ticket.status = TicketStatus.IN_PROGRESS
                ticket.save(update_fields=['status', 'updated_at'])

            # Асинхронное Celery-уведомление участникам
            send_ticket_notification_async(
                event_type='message',
                ticket=ticket,
                request=request,
                actor=request.user,
                new_message=message_obj,
            )

            messages.success(request, 'Сообщение успешно опубликовано.')
        else:
            messages.error(request, 'Ошибка при отправке сообщения. Проверьте формат файлов и текст.')

    return redirect('tickets_app:detail', pk=ticket.pk)


@login_required
@require_POST
def set_ticket_curator(request: HttpRequest) -> HttpResponse:
    """Назначает или сменяет уполномоченного куратора (диспетчера) СДС.

    Доступно исключительно руководству компании и суперпользователям.
    Сохраняет выбранного сотрудника в TicketSettings и фиксирует автора назначения.

    Args:
        request (HttpRequest): Объект HTTP-запроса с POST-параметром curator_id.

    Returns:
        HttpResponse: Перенаправление обратно на реестр заявок.
    """
    if not can_manage_curator(request.user):
        messages.error(request, 'У вас нет полномочий для назначения куратора СДС.')
        return redirect('tickets_app:list')

    curator_id = request.POST.get('curator_id', '').strip()
    settings_obj = TicketSettings.get_settings()

    if not curator_id:
        settings_obj.curator = None
        settings_obj.updated_by = request.user
        settings_obj.save()
        messages.warning(request, 'Куратор СДС снят. Заявки обрабатываются только руководством.')
        return redirect('tickets_app:list')

    try:
        new_curator = DataBaseUser.objects.get(pk=curator_id, is_active=True, is_staff=True)
        settings_obj.curator = new_curator
        settings_obj.updated_by = request.user
        settings_obj.save()
        messages.success(
            request,
            f'Куратором (диспетчером) СДС успешно назначен: {new_curator.get_full_name() or new_curator.username}.',
        )
    except DataBaseUser.DoesNotExist:
        messages.error(request, 'Указанный сотрудник не найден или не является активным штатным специалистом.')

    return redirect('tickets_app:list')

