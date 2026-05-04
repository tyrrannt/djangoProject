# signals.py
import time
from datetime import datetime

from django.db import transaction, IntegrityError
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Counteragent, BiometricConsent


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


@receiver(pre_save, sender=BiometricConsent)
def set_consent_number(sender, instance, **kwargs):
    if instance.consent_number:
        return  # Номер уже задан, не трогаем

    year_str = (instance.consent_date or timezone.now()).strftime('%y')

    # Повторяем до 3 раз при конфликте уникальности (защита для первой записи года)
    for attempt in range(3):
        try:
            with transaction.atomic():
                # Блокируем последнюю запись за текущий год (SELECT ... FOR UPDATE)
                last_consent = BiometricConsent.objects.filter(
                    consent_number__endswith=f"-{year_str}"
                ).select_for_update().order_by('-id').first()

                if last_consent and last_consent.consent_number:
                    try:
                        new_num = int(last_consent.consent_number.split('-')[1]) + 1
                    except (ValueError, IndexError):
                        new_num = 1
                else:
                    new_num = 1

                instance.consent_number = f"БД-{new_num:03d}-{year_str}"
                return  # Успешно сгенерировали, выходим

        except IntegrityError:
            # Если две параллельные транзакции одновременно вставили "001",
            # одна упадёт. Откатываем, ждём и пробуем снова.
            if attempt < 2:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise  # Если после 3 попыток всё ещё конфликт — пробрасываем ошибку