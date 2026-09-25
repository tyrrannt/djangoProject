# signals.py
import logging
import time
from datetime import datetime

from django.db import transaction, IntegrityError
from django.db.models.signals import pre_save, post_save, m2m_changed
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Counteragent, BiometricConsent, DataBaseUser, DataBaseUserWorkProfile

logger = logging.getLogger(__name__)


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


@receiver(post_save, sender=DataBaseUserWorkProfile)
def auto_sync_permissions_on_job_change(sender, instance, **kwargs):
    """Автоматически синхронизирует должностные права пользователя при изменении рабочего профиля или должности.

    Срабатывает при обновлении должности в 1С (OData) или кадровиком в интерфейсе.
    Защищенные роли ЛПК и персональные права сотрудника не затрагиваются.

    Args:
        sender: Модель DataBaseUserWorkProfile.
        instance: Сохраненный экземпляр рабочего профиля.
        **kwargs: Дополнительные параметры сигнала Django.
    """
    try:
        user = getattr(instance, "databaseuser", None)
        if user and user.is_active:
            from administration_app.access_service import UserAccessService

            UserAccessService.sync_user_groups(user)
    except Exception as exc:
        logger.warning("Ошибка автосинхронизации прав при изменении профиля %s: %s", instance, exc)


@receiver(m2m_changed, sender=DataBaseUser.personal_groups.through)
def auto_sync_permissions_on_personal_groups_change(sender, instance, action, **kwargs):
    """Автоматически актуализирует итоговые права пользователя при изменении его персональных прав.

    При добавлении или удалении группы в personal_groups немедленно обновляет
    действующий состав user.groups без перезагрузки системы.

    Args:
        sender: Through-модель отношения personal_groups.
        instance: Экземпляр DataBaseUser.
        action: Тип действия ('post_add', 'post_remove', 'post_clear' и др.).
        **kwargs: Дополнительные параметры сигнала Django.
    """
    if action in ("post_add", "post_remove", "post_clear"):
        try:
            if instance and getattr(instance, "is_active", False):
                from administration_app.access_service import UserAccessService

                UserAccessService.sync_user_groups(instance)
        except Exception as exc:
            logger.warning("Ошибка автосинхронизации прав при изменении personal_groups у %s: %s", instance, exc)