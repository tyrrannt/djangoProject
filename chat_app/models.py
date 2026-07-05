from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class BaseEmojiField:
    def to_python(self, value):
        if isinstance(value, str) or value is None:
            if value is None:
                return value
            else:
                encoded_string = str(value).encode('unicode_escape')
                return encoded_string
        return str(value)

    def from_db_value(self, value, *args, **kwargs):
        if str(value).startswith("b'"):
            value = bytes(str(value).replace("b'", "")[0:-1].replace('\\\\', '\\'), 'utf-8').decode('unicode_escape')
        elif str(value).isascii():
            value = bytes(str(value), 'utf-8').decode('unicode_escape')
            return value
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
        self.message = str(self.message.encode('unicode_escape'))