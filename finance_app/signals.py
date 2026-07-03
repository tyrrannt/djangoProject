from typing import Any
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from finance_app.models import (
    Organization,
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
    FinanceAuditLog,
)
from finance_app.middleware import get_current_user

# Список моделей для аудита
AUDITED_MODELS = [
    Organization,
    FinancialContract,
    FinancialObligation,
    PaymentSchedule,
    PaymentFact,
    DebtSnapshot,
    CreditAgreement,
    CreditPaymentSchedule,
    CreditPaymentFact,
]


@receiver(pre_save)
def audit_pre_save(sender: Any, instance: Any, **kwargs: Any) -> None:
    """
    Сигнал pre_save для отслеживания изменений полей финансовых моделей.

    Args:
        sender: Класс модели.
        instance: Экземпляр модели перед сохранением.
        **kwargs: Дополнительные аргументы.
    """
    if sender not in AUDITED_MODELS:
        return

    if not instance.pk:
        # Это создание объекта, логируется в post_save
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    user = get_current_user()
    content_type = ContentType.objects.get_for_model(sender)

    # Сравниваем поля модели
    for field in sender._meta.fields:
        if field.name in ["id", "ref_key"]:
            continue
        old_val = getattr(old_instance, field.name)
        new_val = getattr(instance, field.name)

        if old_val != new_val:
            FinanceAuditLog.objects.create(
                user=user,
                content_type=content_type,
                object_id=instance.pk,
                field_name=str(field.verbose_name or field.name),
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                action="update",
            )


@receiver(post_save)
def audit_post_save(sender: Any, instance: Any, created: bool, **kwargs: Any) -> None:
    """
    Сигнал post_save для логирования создания финансовых объектов.

    Args:
        sender: Класс модели.
        instance: Экземпляр модели.
        created: Флаг создания нового объекта.
        **kwargs: Дополнительные аргументы.
    """
    if sender not in AUDITED_MODELS:
        return

    if created:
        user = get_current_user()
        content_type = ContentType.objects.get_for_model(sender)

        FinanceAuditLog.objects.create(
            user=user,
            content_type=content_type,
            object_id=instance.pk,
            field_name="Все поля",
            old_value=None,
            new_value=str(instance),
            action="create",
        )


@receiver(post_delete)
def audit_post_delete(sender: Any, instance: Any, **kwargs: Any) -> None:
    """
    Сигнал post_delete для логирования удаления финансовых объектов.

    Args:
        sender: Класс модели.
        instance: Экземпляр модели.
        **kwargs: Дополнительные аргументы.
    """
    if sender not in AUDITED_MODELS:
        return

    user = get_current_user()
    content_type = ContentType.objects.get_for_model(sender)

    FinanceAuditLog.objects.create(
        user=user,
        content_type=content_type,
        object_id=instance.pk,
        field_name="Все поля",
        old_value=str(instance),
        new_value=None,
        action="delete",
    )
