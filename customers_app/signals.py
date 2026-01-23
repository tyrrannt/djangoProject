# signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import Counteragent


@receiver(pre_save, sender=Counteragent)
def prevent_duplicate_counteragent(sender, instance, **kwargs):
    """
    Проверяет дубликаты перед сохранением
    """
    if instance.inn:  # Проверяем только если ИНН указан
        # Ищем существующие записи с таким же ИНН и КПП
        existing = Counteragent.objects.filter(
            inn=instance.inn,
            kpp=instance.kpp
        ).exclude(pk=instance.pk)

        if existing.exists():
            # Можно либо выдать ошибку, либо просто предупредить
            raise ValidationError(
                f"Контрагент с ИНН {instance.inn} и КПП {instance.kpp} уже существует. "
                f"ID существующих записей: {', '.join(str(e.id) for e in existing)}"
            )