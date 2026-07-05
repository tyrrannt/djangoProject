from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChatRoom, Message
from .serializers import ChatRoomSerializer, MessageSerializer

class ChatViewSet(viewsets.ModelViewSet):
    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Для простоты возвращаем все комнаты, в которых пользователь участвует
        # Если participants еще не настроено, можно возвращать вообще все
        user = self.request.user
        return ChatRoom.objects.filter(participants=user).distinct()

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        chat = self.get_object()
        
        if request.method == 'GET':
            messages = chat.messages.all().order_by('timestamp')
            serializer = MessageSerializer(messages, many=True, context={'request': request})
            return Response(serializer.data)
            
        elif request.method == 'POST':
            text = request.data.get('text')
            if not text:
                return Response({'error': 'Message text is required'}, status=status.HTTP_400_BAD_REQUEST)
                
            msg = Message.objects.create(
                room=chat,
                room_name=chat.name,
                username=request.user.username,
                sender=request.user,
                message=text
            )
            serializer = MessageSerializer(msg, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
