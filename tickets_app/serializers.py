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
    sender_position = serializers.SerializerMethodField()

    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'text', 'sender', 'sender_name', 'sender_position', 'is_internal', 'created_at', 'attachments']
        read_only_fields = ['sender', 'is_internal', 'created_at']

    def get_sender_name(self, obj):
        try:
            title = obj.sender.get_title()
            return title if title else obj.sender.username
        except Exception:
            return obj.sender.username

    def get_sender_position(self, obj):
        try:
            return str(obj.sender.user_work_profile.job) if obj.sender.user_work_profile and obj.sender.user_work_profile.job else ""
        except Exception:
            return ""


class TicketSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()
    author_position = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ['id', 'title', 'description', 'status', 'created_at', 'messages', 'parent_ticket', 'attachments', 'author_name', 'author_position']
        read_only_fields = ['status', 'created_at']

    def get_author_name(self, obj):
        try:
            title = obj.author.get_title()
            return title if title else obj.author.username
        except Exception:
            return obj.author.username if obj.author else ""

    def get_author_position(self, obj):
        try:
            return str(obj.author.user_work_profile.job) if obj.author and obj.author.user_work_profile and obj.author.user_work_profile.job else ""
        except Exception:
            return ""

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['author'] = request.user
        return super().create(validated_data)
