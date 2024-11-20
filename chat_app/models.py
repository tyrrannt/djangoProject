from django.db import models

# Create your models here.
# from django.contrib.auth.models import User

class Message(models.Model):
    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
    room_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.room_name} | {self.username}: {self.message}'

    def save(self, *args, **kwargs):
        super(Message, self).save(*args, **kwargs)
        self.message = str(self.message.encode('unicode_escape'))