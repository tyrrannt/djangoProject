from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Ticket, TicketStatus


@receiver(post_save, sender=Ticket)
def ticket_status_changed(sender, instance, created, **kwargs):
    """
    Сигнал для обработки изменений статуса
    """
    if not created:
        # Можно добавить логику при смене статуса
        pass