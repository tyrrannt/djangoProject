from rest_framework import serializers
from .models import Ticket, Message, Attachment


class AttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'file', 'file_url', 'original_name', 'uploaded_at']
        read_only_fields = ['original_name', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'text', 'sender', 'sender_name', 'is_internal', 'created_at', 'attachments']
        read_only_fields = ['sender', 'is_internal', 'created_at']

    def get_sender_name(self, obj):
        return f"{obj.sender.first_name} {obj.sender.last_name}".strip() or obj.sender.username


class TicketSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = ['id', 'title', 'description', 'status', 'created_at', 'messages', 'parent_ticket', 'attachments']
        read_only_fields = ['status', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['author'] = request.user
        return super().create(validated_data)
