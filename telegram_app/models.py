from django.db import models


# Create your models here.
class ChatID(models.Model):
    class Meta:
        verbose_name = "Идентификатор чата телеграм"
        verbose_name_plural = "Идентификатор чата телеграм"

    ref_key = models.CharField(
        verbose_name="Уникальный номер", max_length=37, default=""
    )
    chat_id = models.CharField(verbose_name="Telegram ID", max_length=20, blank=True)

    def __str__(self):
        return self.chat_id


class TelegramNotification(models.Model):
    class Meta:
        verbose_name = "Уведомление телеграм"
        verbose_name_plural = "Уведомления телеграм"

    respondents = models.ManyToManyField(ChatID, verbose_name="Получатели")
    message = models.CharField(
        verbose_name="Сообщение", max_length=256, default="", blank=True
    )
    document_url = models.URLField(verbose_name="Ссылка документ", blank=True)
    document_id = models.CharField(
        verbose_name="UIN документа", default="", max_length=37, null=True, blank=True
    )
    sending_counter = models.IntegerField(verbose_name="Счетчик отправок", default=3)
    send_time = models.TimeField(verbose_name="Время отправки", blank=True, null=True)
