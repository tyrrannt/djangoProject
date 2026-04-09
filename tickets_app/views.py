from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db.models import Q, Prefetch
from django.utils import timezone
from django.urls import reverse

from administration_app.utils import send_notification
from customers_app.models import DataBaseUser
from .models import Ticket, Message, Attachment, TicketStatus
from .forms import TicketCreateForm, TicketUpdateForm, MessageForm, AttachmentForm
from core import logger

# Division 3 — сервисная рассылка (fallback на EMAIL_HOST_USER)
NOTIFICATION_DIVISION = 3


class TicketListView(LoginRequiredMixin, ListView):
    """
    Список заявок (Dashboard)
    - Пользователь видит только свои
    - Сотрудник видит назначенные ему
    - Руководство видит все
    """
    model = Ticket
    template_name = 'tickets_app/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        queryset = Ticket.objects.select_related('author', 'responsible', 'parent_ticket')

        # Руководство видит все
        if user.groups.filter(name='Руководство').exists() or user.is_superuser:
            # Фильтр "Новые без ответственного"
            if self.request.GET.get('unassigned') == '1':
                queryset = queryset.filter(responsible__isnull=True, status=TicketStatus.NEW)
            return queryset

        # Обычный пользователь видит только свои
        return queryset.filter(
            Q(author=user) | Q(responsible=user)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unassigned_count'] = Ticket.objects.filter(
            responsible__isnull=True,
            status=TicketStatus.NEW
        ).count()
        context['done_count'] = Ticket.objects.filter(
            status__in=[TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.REDIRECTED]
        ).count()
        return context


class TicketDetailView(LoginRequiredMixin, DetailView):
    """Детальный просмотр заявки"""
    model = Ticket
    template_name = 'tickets_app/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        user = self.request.user
        is_staff = user.is_superuser or user.groups.filter(name='Руководство').exists()

        # Всегда загружаем все сообщения, фильтрация видимости — в get_context_data
        queryset = Ticket.objects.select_related(
            'author', 'responsible', 'parent_ticket'
        ).prefetch_related(
            Prefetch('messages', queryset=Message.objects.select_related('sender').prefetch_related('attachments')),
            'attachments'
        )

        # Руководство видит все, остальные - только свои или назначенные
        if is_staff:
            return queryset
        return queryset.filter(Q(author=user) | Q(responsible=user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        ticket = self.object
        is_staff = user.is_superuser or user.groups.filter(name='Руководство').exists()
        is_responsible = ticket.responsible == user

        # Фильтруем сообщения: обычные пользователи не видят внутренние заметки
        # Но ответственный по заявке — видит
        if not is_staff and not is_responsible:
            visible_messages = [m for m in ticket.messages.all() if not m.is_internal]
            context['visible_messages'] = visible_messages
            context['visible_messages_count'] = len(visible_messages)
        else:
            context['visible_messages'] = ticket.messages.all()
            context['visible_messages_count'] = ticket.messages.count()

        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    """Создание новой заявки"""
    model = Ticket
    form_class = TicketCreateForm
    template_name = 'tickets_app/ticket_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)

        # Сохраняем вложения к заявке
        files = self.request.FILES.getlist('attachments')
        for f in files:
            Attachment.objects.create(file=f, ticket=self.object)

        # Уведомление руководству о новой заявке
        ticket_url = self.request.build_absolute_uri(
            reverse('tickets_app:detail', kwargs={'pk': self.object.pk})
        )
        context = {
            'event_type': 'new',
            'ticket_title': self.object.title,
            'ticket_description': self.object.description,
            'author_name': str(self.object.author),
            'ticket_pk': self.object.pk,
            'ticket_url': ticket_url,
            'year': timezone.now().year,
        }

        # Находим пользователей руководства для уведомления
        leadership_users = DataBaseUser.objects.filter(
            groups__name='Руководство'
        ).distinct()

        for leader in leadership_users:
            if leader.email:
                try:
                    send_notification(
                        self.request.user,
                        leader,
                        f'Новая заявка: {self.object.title}',
                        'tickets_app/email_notification.html',
                        context,
                        division=NOTIFICATION_DIVISION,
                        document=0,
                    )
                except Exception as e:
                    logger.error(f'Ошибка отправки уведомления руководству: {e}')

        messages.success(self.request, 'Заявка успешно создана')
        return response


class TicketUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Редактирование заявки (назначение ответственного, смена статуса)"""
    model = Ticket
    form_class = TicketUpdateForm
    template_name = 'tickets_app/ticket_form.html'

    def test_func(self):
        ticket = self.get_object()
        user = self.request.user
        # Проверка прав доступа
        if not (user.groups.filter(name='Руководство').exists() or user.is_superuser or ticket.author == user):
            return False
        # Запрет редактирования закрытых/решенных заявок
        if ticket.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
            return False
        return True

    def form_valid(self, form):
        old_ticket = Ticket.objects.get(pk=self.object.pk)

        # Дополнительная проверка статуса (на случай если статус изменился между запросами)
        if old_ticket.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
            messages.error(self.request, 'Нельзя редактировать закрытую или решенную заявку')
            return redirect('tickets_app:detail', pk=self.object.pk)

        response = super().form_valid(form)

        ticket_url = self.request.build_absolute_uri(
            reverse('tickets_app:detail', kwargs={'pk': self.object.pk})
        )

        # Уведомление сотруднику при назначении
        if form.instance.responsible and form.instance.responsible != old_ticket.responsible:
            context = {
                'event_type': 'assigned',
                'ticket_title': form.instance.title,
                'ticket_description': form.instance.description,
                'author_name': str(form.instance.author),
                'ticket_pk': form.instance.pk,
                'ticket_url': ticket_url,
                'year': timezone.now().year,
            }
            try:
                send_notification(
                    self.request.user,
                    form.instance.responsible,
                    f'Вам назначена заявка: {form.instance.title}',
                    'tickets_app/email_notification.html',
                    context,
                    division=NOTIFICATION_DIVISION,
                    document=0,
                )
            except Exception as e:
                logger.error(f'Ошибка отправки уведомления ответственному: {e}')
            messages.success(self.request, 'Ответственный назначен')

        # Уведомление пользователю при решении
        if form.instance.status == TicketStatus.RESOLVED and old_ticket.status != TicketStatus.RESOLVED:
            form.instance.resolved_at = timezone.now()
            form.instance.save(update_fields=['resolved_at'])
            context = {
                'event_type': 'resolved',
                'ticket_title': form.instance.title,
                'ticket_pk': form.instance.pk,
                'ticket_url': ticket_url,
                'year': timezone.now().year,
            }
            try:
                send_notification(
                    self.request.user,
                    form.instance.author,
                    f'Ваша заявка решена: {form.instance.title}',
                    'tickets_app/email_notification.html',
                    context,
                    division=NOTIFICATION_DIVISION,
                    document=0,
                )
            except Exception as e:
                logger.error(f'Ошибка отправки уведомления автору о решении: {e}')
            messages.success(self.request, 'Заявка помечена как решенная')

        return response


def add_message_to_ticket(request, pk):
    """Добавление сообщения к заявке"""
    ticket = get_object_or_404(Ticket, pk=pk)

    # Проверка прав
    is_staff = request.user.groups.filter(name='Руководство').exists() or request.user.is_superuser
    is_author = ticket.author == request.user
    is_responsible = ticket.responsible == request.user

    if not (is_staff or is_author or is_responsible):
        messages.error(request, 'Нет доступа к этой заявке')
        return redirect('tickets_app:list')

    # Проверка статуса - нельзя писать в закрытые/решенные заявки
    if ticket.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        messages.error(request, 'Нельзя добавлять сообщения в закрытую или решенную заявку')
        return redirect('tickets_app:detail', pk=ticket.pk)

    if request.method == 'POST':
        message_form = MessageForm(request.POST)

        if message_form.is_valid():
            message = message_form.save(commit=False)
            message.ticket = ticket
            message.sender = request.user
            message.save()

            # Сохраняем вложения
            files = request.FILES.getlist('attachments')
            for f in files:
                Attachment.objects.create(file=f, message=message)

            # Логика смены статуса
            new_status = request.POST.get('status')  # Получаем статус из формы

            if ticket.status == TicketStatus.NEW:
                # Если статус НЕ передан явно или он пустой (пользователь ничего не выбрал)
                if not new_status:
                    ticket.status = TicketStatus.IN_PROGRESS
                    ticket.save(update_fields=['status'])

                # Если статус ПЕРЕДАН явно (и это делает не автор, а сотрудник/админ)
            elif not is_author and new_status != ticket.status:
                valid_statuses = [s[0] for s in TicketStatus.choices]
                if new_status in valid_statuses:
                    ticket.status = new_status
                    if new_status == TicketStatus.RESOLVED:
                        ticket.resolved_at = timezone.now()
                    ticket.save(update_fields=['status', 'resolved_at'])

            # Уведомления о новом сообщении
            ticket_url = request.build_absolute_uri(
                reverse('tickets_app:detail', kwargs={'pk': ticket.pk})
            )
            context = {
                'event_type': 'message',
                'ticket_title': ticket.title,
                'sender_name': str(request.user),
                'ticket_pk': ticket.pk,
                'ticket_url': ticket_url,
                'year': timezone.now().year,
            }

            notified_emails = set()

            # Уведомляем автора (если сообщение не от него)
            if not is_author and ticket.author.email and ticket.author.email not in notified_emails:
                try:
                    send_notification(
                        request.user,
                        ticket.author,
                        f'Новое сообщение в заявке: {ticket.title}',
                        'tickets_app/email_notification.html',
                        context,
                        division=NOTIFICATION_DIVISION,
                        document=0,
                    )
                    notified_emails.add(ticket.author.email)
                except Exception as e:
                    logger.error(f'Ошибка отправки уведомления автору: {e}')

            # Уведомляем ответственного (если сообщение не от него)
            if not is_responsible and ticket.responsible and ticket.responsible.email:
                if ticket.responsible.email not in notified_emails:
                    try:
                        send_notification(
                            request.user,
                            ticket.responsible,
                            f'Новое сообщение в заявке: {ticket.title}',
                            'tickets_app/email_notification.html',
                            context,
                            division=NOTIFICATION_DIVISION,
                            document=0,
                        )
                        notified_emails.add(ticket.responsible.email)
                    except Exception as e:
                        logger.error(f'Ошибка отправки уведомления ответственному: {e}')

            messages.success(request, 'Сообщение добавлено')
            return redirect('tickets_app:detail', pk=ticket.pk)
    else:
        message_form = MessageForm()

    # Перенаправляем на detail — форма рендерится там
    return redirect('tickets_app:detail', pk=ticket.pk)
