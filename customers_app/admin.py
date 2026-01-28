# Register your models here.
from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.contrib import messages
from django.db import transaction
from django.apps import apps
from django.db.models import ForeignKey, OneToOneField
from django.core.exceptions import FieldError
import logging

logger = logging.getLogger(__name__)


from .models import (
    DataBaseUser,
    Job,
    Division,
    Counteragent,
    Posts,
    AccessLevel,
    DataBaseUserProfile,
    Citizenships,
    IdentityDocuments,
    DataBaseUserWorkProfile,
    HarmfulWorkingConditions,
    ViewDocumentsPhysical,
    HistoryChange,
    HappyBirthdayGreetings,
    Affiliation,
    VacationScheduleList,
    VacationSchedule,
    CounteragentDocuments,
    UserStats,
    Apartments,
)


class CustomUserAdmin(UserAdmin):
    """
    Расширяем модель UserAdmin
    fieldsets: исходный набор полей формы
    *UserAdmin.fieldsets: добавляем расширенный набор полей формы,
        тип: кортеж содержащий ('заголовок группы по вашему выбору', {словарь c новыми полями})
    """
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': (
            'title', 'first_name', 'last_name', 'surname', 'email', 'birthday')}),
        ('Profile info', {'fields': (
            'avatar', 'address', 'type_users', 'service_number', 'user_access', 'personal_phone', 'gender',
            'user_work_profile', 'user_profile', 'ref_key', 'person_ref_key', 'passphrase', 'telegram_id', 'is_ppa')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions', 'type_of_role')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'birthday'),
        }),
    )

    list_display = ("pk", "username", "last_login", "last_name", "first_name", "surname", "birthday", "email", "is_active", 'is_ppa')
    search_fields = ('pk', 'title', 'ref_key', 'person_ref_key')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'is_ppa')
    list_editable = ('is_active', 'is_ppa')
    list_per_page = 50
    ordering = ('last_name', 'first_name')
    empty_value_display = '-empty-'
    actions = ['activate_users', 'deactivate_users']

    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
    activate_users.short_description = "Активируйте выбранных пользователей"

    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_users.short_description = "Деактивировать выбранных пользователей"


admin.site.register(DataBaseUser, CustomUserAdmin)
admin.site.register(Job)
admin.site.register(AccessLevel)
admin.site.register(DataBaseUserProfile)
admin.site.register(Citizenships)
admin.site.register(DataBaseUserWorkProfile)
admin.site.register(HarmfulWorkingConditions)
admin.site.register(ViewDocumentsPhysical)
admin.site.register(HistoryChange)
admin.site.register(HappyBirthdayGreetings)
admin.site.register(Affiliation)
admin.site.register(VacationScheduleList)
admin.site.register(VacationSchedule)


@admin.register(IdentityDocuments)
class IdentityDocumentsAdmin(admin.ModelAdmin):
    list_display = ("series", "number", "issued_by_whom", "date_of_issue",
                    "division_code",)  #


@admin.register(CounteragentDocuments)
class CounteragentDocumentsAdmin(admin.ModelAdmin):
    list_display = ("package", "date_of_creation", "description", "document",)  #


# @admin.register(Counteragent)
# class CounteragentAdmin(admin.ModelAdmin):
#     list_display = ("pk", "short_name", "inn", "kpp", "ogrn", "type_counteragent",)
#     search_fields = ("short_name", "inn", "kpp", "ogrn")
#     ordering = ('pk',)

@admin.register(Posts)
class PostsAdmin(admin.ModelAdmin):
    list_display = ("pk", "post_title", "creation_date", "allowed_placed", "email_send", "post_date_start", "post_date_end")
    search_fields = ("post_title", "creation_date")
    ordering = ('-pk',)
    list_filter = ("creation_date", "allowed_placed", "email_send",)

@admin.register(Division)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ("pk", "code", "name", "active",)
    search_fields = ("name", "code",)
    ordering = ('code',)

@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = ("pk", "score", "level", "lines_cleared", "games_played")
    # search_fields = ("name", "code",)
    ordering = ('created_at',)

@admin.register(Apartments)
class ApartmentsAdmin(admin.ModelAdmin):
    list_display = ("pk", "title", "place", "beds_number",)
    search_fields = ("title",)
    ordering = ('pk',)


@admin.register(Counteragent)
class CounteragentAdmin(admin.ModelAdmin):
    list_display = ["pk", 'short_name', 'inn', 'kpp', 'type_counteragent', 'duplicates_info']
    list_filter = ['type_counteragent']
    search_fields = ['short_name', 'inn', 'kpp']
    actions = ['find_and_mark_duplicates', 'merge_duplicates']
    ordering = ('pk',)

    def duplicates_info(self, obj):
        """Отображает информацию о дубликатах в списке"""
        duplicates = obj.get_potential_duplicates(obj)
        if duplicates.exists():
            count = duplicates.count()
            url = reverse('admin:customers_app_counteragent_changelist')
            return format_html(
                '<span style="color: red;">⚠ Дубликатов: {}</span><br>'
                '<a href="{}?inn={}" target="_blank">Показать</a>',
                count, url, obj.inn
            )
        return "✓ Уникальный"

    duplicates_info.short_description = "Дубликаты"

    def find_and_mark_duplicates(self, request, queryset):
        """Находит и помечает дубликаты"""
        all_duplicates = Counteragent.find_duplicates_by_inn_kpp()

        if not all_duplicates:
            self.message_user(request, "Дубликатов не найдено", messages.INFO)
            return

        message_parts = ["<strong>Найдены дубликаты:</strong>"]

        for (inn, kpp), objects in all_duplicates.items():
            if objects and len(objects) > 1:
                ids = [str(obj.id) for obj in objects]
                names = [obj.short_name or f"ID:{obj.id}" for obj in objects]
                message_parts.append(
                    f"ИНН: <strong>{inn or '—'}</strong>, КПП: <strong>{kpp or '—'}</strong> - "
                    f"ID: {', '.join(ids)}, Названия: {', '.join(names)}"
                )

        total_count = sum(len(objects) for _, objects in all_duplicates.items() if len(objects) > 1)
        message_parts.insert(1, f"<br>Всего групп дубликатов: <strong>{len(all_duplicates)}</strong>")
        message_parts.insert(2, f"Всего дублирующих записей: <strong>{total_count}</strong>")

        self.message_user(request, format_html("<br>".join(message_parts)), messages.WARNING)

    find_and_mark_duplicates.short_description = "Найти дубликаты"

    def merge_duplicates(self, request, queryset):
        """
        Объединяет выбранные дубликаты
        Основной объект - с минимальным PK, дубликаты удаляются после переноса связей
        """
        # Группируем по ИНН и КПП
        grouped = {}
        for obj in queryset:
            if obj.inn:  # Объединяем только если есть ИНН
                key = (obj.inn, obj.kpp)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(obj)

        if not grouped:
            self.message_user(request, "Нет объектов с ИНН для объединения", messages.WARNING)
            return

        merged_groups = 0
        merged_records = 0
        failed_groups = 0

        # ОБРАБАТЫВАЕМ КАЖДУЮ ГРУППУ ОТДЕЛЬНО
        for (inn, kpp), objects in grouped.items():
            if len(objects) > 1:
                try:
                    # ОТДЕЛЬНАЯ ТРАНЗАКЦИЯ ДЛЯ КАЖДОЙ ГРУППЫ
                    with transaction.atomic():
                        # Сортируем по PK, чтобы взять основной объект (с минимальным PK)
                        objects.sort(key=lambda x: x.pk)
                        main_obj = objects[0]  # Основной объект
                        duplicates = objects[1:]  # Дубликаты для удаления

                        # Обновляем все связанные объекты
                        update_info = self._update_related_objects_safe(main_obj, duplicates)

                        # Удаляем дубликаты
                        for dup in duplicates:
                            dup.delete()
                            merged_records += 1

                        merged_groups += 1

                        # Логируем успешное объединение
                        success_msg = f"✓ Объединена группа ИНН:{inn}, КПП:{kpp or '—'}. "
                        success_msg += f"Основной: ID:{main_obj.pk}, удалено: {len(duplicates)}"

                        if update_info['total_updated'] > 0:
                            success_msg += f", обновлено записей: {update_info['total_updated']}"
                            if update_info['models_updated']:
                                success_msg += f" ({', '.join(update_info['models_updated'])})"

                        self.message_user(request, success_msg, messages.INFO)

                except Exception as e:
                    failed_groups += 1
                    logger.error(f"Ошибка при объединении группы ИНН:{inn}, КПП:{kpp}: {str(e)}", exc_info=True)

                    # Простое сообщение об ошибке
                    try:
                        self.message_user(
                            request,
                            f"✗ Ошибка при объединении группы ИНН:{inn}, КПП:{kpp or '—'}: {str(e)[:100]}...",
                            messages.ERROR
                        )
                    except:
                        pass

        # Итоговое сообщение
        try:
            if merged_groups > 0:
                success_msg = (
                    f"<strong>Успешно объединено:</strong><br>"
                    f"• Групп: {merged_groups}<br>"
                    f"• Записей удалено: {merged_records}<br>"
                )
                if failed_groups > 0:
                    success_msg += f"<br><strong>Не удалось объединить:</strong> {failed_groups} групп"

                self.message_user(request, format_html(success_msg), messages.SUCCESS)
            else:
                self.message_user(request, "Не удалось объединить ни одну группу", messages.WARNING)

        except Exception as e:
            logger.error(f"Ошибка при отправке итогового сообщения: {e}")

    merge_duplicates.short_description = "Объединить выбранные дубликаты"

    def _get_all_related_fields(self):
        """
        Возвращает ВСЕ поля, которые ссылаются на Counteragent
        Включая ForeignKey и OneToOneField
        """
        related_fields = []
        all_models = apps.get_models()

        for model in all_models:
            # Пропускаем саму модель Counteragent
            if model == Counteragent:
                continue

            for field in model._meta.get_fields():
                # Проверяем ForeignKey и OneToOneField
                if isinstance(field, (ForeignKey, OneToOneField)):
                    # Получаем связанную модель
                    try:
                        related_model = field.related_model
                        if related_model and related_model == Counteragent:
                            related_fields.append({
                                'model': model,
                                'field': field,
                                'field_name': field.name,  # Имя поля, например "counteragent"
                                'verbose_name': model._meta.verbose_name,
                                'app_label': model._meta.app_label,
                                'model_name': model._meta.model_name,
                            })
                    except AttributeError:
                        # Если не удалось получить related_model, пропускаем
                        continue

        return related_fields

    def _update_related_objects_safe(self, main_obj, duplicates):
        """
        Безопасное обновление связанных объектов с обработкой ошибок
        Возвращает информацию об обновлении
        """
        update_info = {
            'total_updated': 0,
            'models_updated': [],
            'errors': []
        }

        # Получаем все связанные поля
        related_fields = self._get_all_related_fields()

        for dup in duplicates:
            # Для каждого дубликата обновляем все связанные модели
            for rel_info in related_fields:
                model = rel_info['model']
                field_name = rel_info['field_name']
                model_display = f"{rel_info['app_label']}.{rel_info['model_name']}"

                try:
                    # Фильтруем объекты, которые ссылаются на текущий дубликат
                    filter_kwargs = {field_name: dup}
                    related_queryset = model.objects.filter(**filter_kwargs)

                    # Обновляем ссылки на основной объект
                    updated_count = related_queryset.update(**{field_name: main_obj})

                    if updated_count > 0:
                        update_info['total_updated'] += updated_count
                        if model_display not in update_info['models_updated']:
                            update_info['models_updated'].append(model_display)

                        logger.info(
                            f"Обновлено {updated_count} записей в {model_display}.{field_name} "
                            f"с {dup.id} на {main_obj.id}"
                        )

                except FieldError as fe:
                    # Поле не найдено в модели
                    error_msg = f"Поле {field_name} не найдено в модели {model_display}: {fe}"
                    update_info['errors'].append(error_msg)
                    logger.warning(error_msg)
                    continue
                except Exception as e:
                    # Другие ошибки
                    error_msg = f"Ошибка при обновлении {model_display}.{field_name}: {e}"
                    update_info['errors'].append(error_msg)
                    logger.error(error_msg, exc_info=True)
                    # Продолжаем с другими моделями
                    continue

        return update_info

    # Альтернативный метод с диагностикой
    def diagnose_related_models(self, request, queryset):
        """
        Диагностика - показывает какие модели ссылаются на выбранные контрагенты
        """
        if queryset.count() > 5:
            self.message_user(request, "Выберите не более 5 контрагентов для диагностики", messages.WARNING)
            return

        related_fields = self._get_all_related_fields()

        message_parts = ["<strong>Модели, ссылающиеся на Counteragent:</strong>"]

        for rel_info in related_fields:
            model_display = f"{rel_info['app_label']}.{rel_info['model_name']}"
            field_name = rel_info['field_name']
            verbose_name = rel_info['verbose_name']

            # Проверяем, есть ли записи для выбранных контрагентов
            total_count = 0
            for obj in queryset:
                try:
                    filter_kwargs = {field_name: obj}
                    count = rel_info['model'].objects.filter(**filter_kwargs).count()
                    total_count += count
                except Exception as e:
                    count = f"ошибка: {e}"

            message_parts.append(
                f"• {model_display} ({verbose_name}) - поле: <code>{field_name}</code>, "
                f"связей с выбранными: {total_count}"
            )

        self.message_user(request, format_html("<br>".join(message_parts)), messages.INFO)

    diagnose_related_models.short_description = "Диагностика связанных моделей"

    # Улучшенная версия merge с диагностикой
    def merge_duplicates_with_diagnosis(self, request, queryset):
        """
        Объединение с предварительной диагностикой
        """
        # 1. Диагностика
        self.diagnose_related_models(request, queryset)

        # 2. Продолжение с объединением
        return self.merge_duplicates(request, queryset)

    merge_duplicates_with_diagnosis.short_description = "Объединить с диагностикой"