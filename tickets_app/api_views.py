from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Ticket, Message, Attachment
from .serializers import TicketSerializer, MessageSerializer

class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Ticket.objects.all().order_by('-updated_at', '-created_at')
        return Ticket.objects.filter(author=user).order_by('-updated_at', '-created_at')

    def perform_create(self, serializer):
        ticket = serializer.save()
        files = self.request.FILES.getlist('attachments')
        for f in files:
            Attachment.objects.create(ticket=ticket, file=f)

    @action(detail=True, methods=['post'])
    def message(self, request, pk=None):
        ticket = self.get_object()
        text = request.data.get('text')
        if not text:
            return Response({'error': 'Текст сообщения обязателен'}, status=status.HTTP_400_BAD_REQUEST)
        
        msg = Message.objects.create(
            ticket=ticket,
            sender=request.user,
            text=text
        )
        
        files = request.FILES.getlist('attachments')
        for f in files:
            Attachment.objects.create(message=msg, file=f)
        
        # Обновляем ticket updated_at
        ticket.save()
        
        serializer = MessageSerializer(msg)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def change_status(self, request, pk=None):
        ticket = self.get_object()
        user = request.user
        
        if not (user.is_superuser or user.groups.filter(name='Руководство').exists() or ticket.responsible == user):
            return Response({'error': 'Нет прав для изменения статуса'}, status=status.HTTP_403_FORBIDDEN)
            
        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'Не указан новый статус'}, status=status.HTTP_400_BAD_REQUEST)
            
        from .models import TicketStatus
        valid_statuses = [s[0] for s in TicketStatus.choices]
        if new_status not in valid_statuses:
            return Response({'error': 'Неверный статус'}, status=status.HTTP_400_BAD_REQUEST)
            
        ticket.status = new_status
        if new_status == TicketStatus.RESOLVED:
            from django.utils import timezone
            ticket.resolved_at = timezone.now()
        ticket.save(update_fields=['status', 'resolved_at'] if new_status == TicketStatus.RESOLVED else ['status'])
        
        serializer = self.get_serializer(ticket)
        return Response(serializer.data)
