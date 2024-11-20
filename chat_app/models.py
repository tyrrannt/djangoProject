from django.db import models

# Create your models here.
# from django.contrib.auth.models import User
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

class Message(models.Model):
    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
    room_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    message = CustomEmojiTextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.room_name} | {self.username}: {self.message}'

    def save(self, *args, **kwargs):
        super(Message, self).save(*args, **kwargs)
        self.message = str(self.message.encode('unicode_escape'))