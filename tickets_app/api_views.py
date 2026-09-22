"""Эндпоинты REST API модуля заявок и добровольных сообщений (tickets_app.api_views).

Предоставляет программный доступ для мобильных приложений и внешних сервисов:
- Просмотр списка и карточек заявок;
- Создание заявок и отправка сообщений;
- Смена статусов с асинхронными Celery-уведомлениями.
"""

from typing import Any

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from customers_app.models import DataBaseUser
from .models import Attachment, Message, Ticket, TicketStatus
from .serializers import MessageSerializer, TicketSerializer
from .services import is_ticket_manager, save_ticket_attachments, send_ticket_notification_async


class TicketViewSet(viewsets.ModelViewSet):
    """ViewSet для операций с добровольными сообщениями и заявками."""

    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает заявки с учетом прав доступа пользователя."""
        user = self.request.user
        is_manager = is_ticket_manager(user)

        if is_manager:
            return Ticket.objects.all().select_related('author', 'responsible', 'parent_ticket').order_by('-created_at')

        return (
            Ticket.objects.filter(Q(author=user) | Q(responsible=user))
            .select_related('author', 'responsible', 'parent_ticket')
            .order_by('-created_at')
        )

    def perform_create(self, serializer: TicketSerializer) -> None:
        """Сохраняет новую заявку, вложения и отправляет асинхронное уведомление."""
        ticket: Ticket = serializer.save()
        files = self.request.FILES.getlist('attachments')
        if files:
            save_ticket_attachments(files, ticket=ticket)

        send_ticket_notification_async(
            event_type='new',
            ticket=ticket,
            request=self.request,
            actor=self.request.user,
        )

    @action(detail=True, methods=['post'])
    def message(self, request: Request, pk: Any = None) -> Response:
        """Добавляет новое сообщение в переписку по заявке."""
        ticket: Ticket = self.get_object()

        if ticket.is_closed_or_resolved:
            return Response(
                {'error': 'Нельзя добавлять сообщения в закрытую или решенную заявку.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text = request.data.get('text', '').strip()
        if not text:
            return Response({'error': 'Текст сообщения обязателен.'}, status=status.HTTP_400_BAD_REQUEST)

        is_manager = is_ticket_manager(request.user)
        is_responsible = ticket.responsible == request.user
        is_internal = bool(request.data.get('is_internal', False))

        # Обычный пользователь не может отправлять скрытые служебные заметки
        if not is_manager and not is_responsible:
            is_internal = False

        msg = Message.objects.create(
            ticket=ticket,
            sender=request.user,
            text=text,
            is_internal=is_internal,
        )

        files = request.FILES.getlist('attachments')
        if files:
            save_ticket_attachments(files, message=msg)

        # Автоматический перевод в работу при ответе сотрудника/руководителя
        if ticket.status == TicketStatus.NEW and (is_manager or is_responsible) and ticket.author != request.user:
            ticket.status = TicketStatus.IN_PROGRESS
            ticket.save(update_fields=['status', 'updated_at'])
        else:
            ticket.save(update_fields=['updated_at'])

        # Асинхронное уведомление через Celery
        send_ticket_notification_async(
            event_type='message',
            ticket=ticket,
            request=request,
            actor=request.user,
            new_message=msg,
        )

        serializer = MessageSerializer(msg, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def change_status(self, request: Request, pk: Any = None) -> Response:
        """Изменяет статус обработки заявки (для руководства, куратора и ответственного)."""
        ticket: Ticket = self.get_object()
        user = request.user

        is_manager = is_ticket_manager(user)
        is_responsible = ticket.responsible == user

        if not (is_manager or is_responsible):
            return Response({'error': 'Недостаточно прав для изменения статуса.'}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        valid_statuses = [s[0] for s in TicketStatus.choices]
        if not new_status or new_status not in valid_statuses:
            return Response({'error': 'Неверный статус заявки.'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = ticket.status
        ticket.status = new_status
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = timezone.now()
        else:
            ticket.resolved_at = None

        ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])

        if new_status == TicketStatus.RESOLVED and old_status != TicketStatus.RESOLVED:
            send_ticket_notification_async(
                event_type='resolved',
                ticket=ticket,
                request=request,
                actor=request.user,
            )

        serializer = self.get_serializer(ticket)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def assign_responsible(self, request: Request, pk: Any = None) -> Response:
        """Назначает или сменяет ответственного исполнителя по заявке (для руководства и куратора)."""
        ticket: Ticket = self.get_object()
        user = request.user
        if not is_ticket_manager(user):
            return Response(
                {'error': 'Недостаточно прав для назначения ответственного специалиста.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        resp_id = request.data.get('responsible')
        if not resp_id:
            return Response({'error': 'Параметр responsible обязателен.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resp_user = DataBaseUser.objects.get(pk=resp_id, is_active=True)
        except DataBaseUser.DoesNotExist:
            return Response(
                {'error': 'Сотрудник не найден или заблокирован.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_resp = ticket.responsible
        ticket.responsible = resp_user
        if ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.IN_PROGRESS
        ticket.save()

        if resp_user != old_resp:
            send_ticket_notification_async(
                event_type='assigned',
                ticket=ticket,
                request=request,
                actor=request.user,
            )

        serializer = self.get_serializer(ticket)
        return Response(serializer.data)
