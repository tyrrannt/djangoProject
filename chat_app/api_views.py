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

    def perform_create(self, serializer):
        chat = serializer.save()
        chat.participants.add(self.request.user)

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

    @action(detail=False, methods=['get'])
    def web_auth_token(self, request):
        from django.core.cache import cache
        from django.utils.crypto import get_random_string
        token = get_random_string(length=32)
        cache.set(token, request.user.id, timeout=60)
        return Response({'token': token})

    @action(detail=True, methods=['get', 'post'])
    def participants(self, request, pk=None):
        chat = self.get_object()
        
        if request.method == 'GET':
            participants = chat.participants.all()
            data = [{
                'id': p.id, 
                'username': p.username, 
                'first_name': getattr(p, 'first_name', ''), 
                'last_name': getattr(p, 'last_name', '')
            } for p in participants]
            return Response(data)
            
        elif request.method == 'POST':
            username = request.data.get('username')
            if not username:
                return Response({'error': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)
                
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user_to_add = User.objects.get(username=username)
                chat.participants.add(user_to_add)

                # Send WebSocket notification (like in the web version)
                from asgiref.sync import async_to_sync
                from channels.layers import get_channel_layer
                from django.urls import reverse
                
                channel_layer = get_channel_layer()
                room_url = request.build_absolute_uri(reverse('chat_app:room', args=[chat.name]))
                message_html = f'Вас приглашают присоединиться к чату: <strong>{chat.name}</strong>. <br><a href="{room_url}" class="btn btn-xs btn-primary mt-1">Присоединиться</a>'
                
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_to_add.id}",
                    {
                        "type": "private_message",
                        "message": message_html,
                        "from": request.user.pk,
                        "from_name": getattr(request.user, 'title', request.user.username)
                    }
                )

                return Response({'status': 'success', 'user_id': user_to_add.id})
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def available_users(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        users = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by('last_name', 'first_name', 'username')
        data = [{
            'id': u.id,
            'username': u.username,
            'first_name': getattr(u, 'first_name', ''),
            'last_name': getattr(u, 'last_name', ''),
            'title': getattr(u, 'title', u.username)
        } for u in users]
        return Response(data)
