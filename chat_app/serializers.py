from rest_framework import serializers
from .models import ChatRoom, Message
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatRoomSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = ['id', 'name', 'last_message', 'last_message_time', 'unread_count']

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-timestamp').first()
        if last_msg:
            return last_msg.message
        return None

    def get_last_message_time(self, obj):
        last_msg = obj.messages.order_by('-timestamp').first()
        if last_msg:
            return last_msg.timestamp
        return None

    def get_unread_count(self, obj):
        # Placeholder
        return 0

class MessageSerializer(serializers.ModelSerializer):
    chat_id = serializers.IntegerField(source='room_id', read_only=True)
    sender_id = serializers.IntegerField(source='sender.id', read_only=True)
    sender_name = serializers.SerializerMethodField()
    text = serializers.CharField(source='message')
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'chat_id', 'sender_id', 'sender_name', 'text', 'timestamp', 'is_mine']

    def get_sender_name(self, obj):
        if obj.sender:
            return obj.sender.get_full_name() or obj.sender.username
        return obj.username

    def get_is_mine(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if obj.sender:
                return obj.sender == request.user
            return obj.username == request.user.username
        return False
