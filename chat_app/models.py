from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class BaseEmojiField:
    def get_prep_value(self, value):
        if value is None:
            return value
        return str(str(value).encode('unicode_escape'))

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        val_str = str(value)
        if val_str.startswith("b'") and val_str.endswith("'"):
            try:
                # Extract the bytes string from inside "b'....'"
                inner = val_str[2:-1].replace('\\\\', '\\')
                return bytes(inner, 'utf-8').decode('unicode_escape')
            except Exception:
                pass
        elif val_str.isascii():
            try:
                return bytes(val_str, 'utf-8').decode('unicode_escape')
            except Exception:
                pass
        return value

class CustomEmojiCharField(BaseEmojiField , models.CharField):
    pass

class CustomEmojiTextField(BaseEmojiField ,models.TextField):
    pass

class ChatRoom(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название комнаты")
    participants = models.ManyToManyField(User, related_name='chat_rooms', blank=True, verbose_name="Участники")

    class Meta:
        verbose_name = 'Чат'
        verbose_name_plural = 'Чаты'

    def __str__(self):
        return self.name

class Message(models.Model):
    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
    
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    room_name = models.CharField(max_length=255) # Храним для обратной совместимости
    username = models.CharField(max_length=255)
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    message = CustomEmojiTextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.room_name} | {self.username}: {self.message}'

    def save(self, *args, **kwargs):
        if not self.room and self.room_name:
            room, _ = ChatRoom.objects.get_or_create(name=self.room_name)
            self.room = room
        super(Message, self).save(*args, **kwargs)