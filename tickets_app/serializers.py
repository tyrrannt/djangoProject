"""Сериализаторы данных REST API модуля добровольных сообщений (tickets_app.serializers).

Обеспечивает сериализацию заявок, переписки и вложений, а также строгое сокрытие
внутренних служебных заметок от заявителей при формировании ответов API.
"""

from typing import Any, Dict, List, Optional

from rest_framework import serializers

from .models import Attachment, Message, Ticket, TicketStatus


class AttachmentSerializer(serializers.ModelSerializer):
    """Сериализатор прикрепленных документов и фотографий."""

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'file', 'file_url', 'original_name', 'uploaded_at']
        read_only_fields = ['original_name', 'uploaded_at']

    def get_file_url(self, obj: Attachment) -> Optional[str]:
        """Возвращает абсолютный URL для скачивания файла."""
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class MessageSerializer(serializers.ModelSerializer):
    """Сериализатор сообщений переписки по заявке."""

    sender_name = serializers.SerializerMethodField()
    sender_position = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            'id',
            'text',
            'sender',
            'sender_name',
            'sender_position',
            'is_internal',
            'created_at',
            'attachments',
        ]
        read_only_fields = ['sender', 'created_at']

    def get_sender_name(self, obj: Message) -> str:
        """Возвращает читаемое ФИО или логин отправителя."""
        try:
            title = obj.sender.get_title()
            return title if title else obj.sender.username
        except Exception:
            return obj.sender.username

    def get_sender_position(self, obj: Message) -> str:
        """Возвращает должность отправителя из профиля сотрудника."""
        try:
            profile = getattr(obj.sender, 'user_work_profile', None)
            return str(profile.job) if profile and profile.job else ""
        except Exception:
            return ""


class TicketSerializer(serializers.ModelSerializer):
    """Сериализатор заявки СДС с фильтрацией закрытых служебных заметок."""

    messages = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()
    author_position = serializers.SerializerMethodField()
    responsible_name = serializers.SerializerMethodField()
    can_change_status = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            'id',
            'title',
            'description',
            'status',
            'created_at',
            'updated_at',
            'resolved_at',
            'messages',
            'parent_ticket',
            'attachments',
            'author_name',
            'author_position',
            'responsible',
            'responsible_name',
            'can_change_status',
        ]
        read_only_fields = ['status', 'created_at', 'updated_at', 'resolved_at']

    def get_messages(self, obj: Ticket) -> List[Dict[str, Any]]:
        """Фильтрует внутренние заметки руководства от обычных заявителей."""
        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None

        is_manager = False
        is_responsible = False
        if user:
            is_manager = user.is_superuser or user.groups.filter(name='Руководство').exists()
            is_responsible = obj.responsible == user

        all_msgs = obj.messages.select_related('sender').prefetch_related('attachments').order_by('created_at')
        if not is_manager and not is_responsible:
            all_msgs = all_msgs.filter(is_internal=False)

        return MessageSerializer(all_msgs, many=True, context=self.context).data

    def get_author_name(self, obj: Ticket) -> str:
        """Возвращает читаемое имя автора."""
        try:
            title = obj.author.get_title()
            return title if title else obj.author.username
        except Exception:
            return obj.author.username if obj.author else ""

    def get_author_position(self, obj: Ticket) -> str:
        """Возвращает должность автора."""
        try:
            profile = getattr(obj.author, 'user_work_profile', None)
            return str(profile.job) if profile and profile.job else ""
        except Exception:
            return ""

    def get_responsible_name(self, obj: Ticket) -> str:
        """Возвращает имя ответственного специалиста."""
        if not obj.responsible:
            return ""
        try:
            title = obj.responsible.get_title()
            return title if title else obj.responsible.username
        except Exception:
            return obj.responsible.username

    def get_can_change_status(self, obj: Ticket) -> bool:
        """Проверяет право текущего пользователя на смену статуса заявки."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        return user.is_superuser or user.groups.filter(name='Руководство').exists() or obj.responsible == user

    def validate_parent_ticket(self, value: Optional[Ticket]) -> Optional[Ticket]:
        """Валидирует право на повторное обжалование заявки."""
        if not value:
            return value

        request = self.context.get('request')
        user = request.user if request and request.user.is_authenticated else None

        if user and value.author != user:
            raise serializers.ValidationError('Разрешено обжаловать только собственные заявки.')

        if not value.is_closed_or_resolved:
            raise serializers.ValidationError('Обжалование возможно только для решенных или закрытых заявок.')

        return value

    def create(self, validated_data: Dict[str, Any]) -> Ticket:
        """Создает заявку с привязкой к текущему авторизованному автору."""
        request = self.context.get('request')
        validated_data['author'] = request.user
        return super().create(validated_data)
