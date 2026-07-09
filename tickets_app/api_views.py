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
