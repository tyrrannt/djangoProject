"""
Утилита для замены одного элемента справочника на другой.
Используется при удалении дубликатов справочников.
"""

from django.db import models


def replace_reference(model_class, old_obj, new_obj):
    """
    Заменяет old_obj на new_obj во всех связанных моделях.

    Args:
        model_class: Класс модели-справочника (DestLit, LocationRef, AircraftType, ContractorStatus)
        old_obj: Экземпляр, который нужно удалить
        new_obj: Экземпляр, на который нужно заменить

    Returns:
        dict: Статистика замен по таблицам
    """
    if old_obj.pk == new_obj.pk:
        raise ValueError("Нельзя заменить элемент на самого себя")

    stats = {"replaced": {}, "errors": {}}

    # Находим все модели с FK на данный справочник
    related_models = model_class._meta.related_objects

    for related in related_models:
        if not isinstance(related.field, models.ForeignKey):
            continue

        related_model = related.related_model
        field_name = related.field.name

        try:
            # Обновляем FK: old → new
            count = related_model.objects.filter(**{field_name: old_obj}).update(**{field_name: new_obj})
            if count > 0:
                stats["replaced"][f"{related_model._meta.verbose_name} ({field_name})"] = count
        except Exception as e:
            stats["errors"][f"{related_model._meta.verbose_name} ({field_name})"] = str(e)

    # Удаляем старый элемент
    old_obj.delete()
    stats["deleted"] = str(old_obj)

    return stats
