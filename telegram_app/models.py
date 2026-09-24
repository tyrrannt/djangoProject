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
    is_active = models.BooleanField(verbose_name="Активна ли подписка", default=True)

    # Матрица персональных уведомлений
    notify_memos = models.BooleanField(
        verbose_name="Уведомления о служебных записках", default=True
    )
    notify_tasks = models.BooleanField(
        verbose_name="Уведомления о задачах", default=True
    )
    notify_birthdays = models.BooleanField(
        verbose_name="Уведомления о днях рождения", default=True
    )
    notify_emails = models.BooleanField(
        verbose_name="Уведомления о корпоративной почте", default=True
    )
    notify_flights = models.BooleanField(
        verbose_name="Уведомления о рейсах и экипажах", default=True
    )

    def __str__(self):
        return f"{self.chat_id} ({'активен' if self.is_active else 'отключен'})"


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
    send_date = models.DateField(verbose_name="Дата отправки", blank=True, null=True)

    def __str__(self):
        return self.message
