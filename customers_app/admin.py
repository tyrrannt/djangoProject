from typing import Optional, Tuple, Dict, Any, List
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.contrib import messages
from django.db import transaction
from django.apps import apps
from django.db.models import ForeignKey, OneToOneField
from django.core.exceptions import FieldError
import logging

from django.utils.safestring import mark_safe

from hrdepartment_app.models import ApprovalOficialMemoProcess

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
    Apartments, ApartmentBooking, BiometricConsent, ConsentType,
    PushSubscription, UserPasskey, UserCertificate,
    OrgStructure, OrgStructureNode, OrgNodeLeadershipHistory,
)
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


class CustomUserAdmin(BaseUserAdmin, ModelAdmin):
    """
    Расширенное администрирование пользователей с интеграцией Django Unfold.
    """
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': (
            'title', 'first_name', 'last_name', 'surname', 'email', 'birthday', 'employment_contract',
            'employment_contract_date')}),
        ('Profile info', {'fields': (
            'avatar', 'address', 'type_users', 'service_number', 'user_access', 'personal_phone', 'gender',
            'user_work_profile', 'user_profile', 'ref_key', 'person_ref_key', 'passphrase', 'telegram_id', 'is_ppa')}),
        ('Permissions',
         {'fields': ('is_active', 'is_staff', 'is_superuser', 'personal_groups', 'groups', 'user_permissions', 'type_of_role')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    filter_horizontal = ('personal_groups', 'groups', 'user_permissions')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'birthday'),
        }),
    )

    list_display = (
        "display_user_header",
        "birthday",
        "email",
        "display_role",
        "display_status",
        "is_ppa",
    )
    search_fields = ('pk', 'title', 'ref_key', 'person_ref_key', 'username', 'last_name', 'first_name')
    list_filter = (
        'is_active',
        'is_staff',
        'is_superuser',
        'is_ppa',
        'groups',
    )
    list_per_page = 50
    ordering = ('last_name', 'first_name')
    compressed_fields = True
    warn_unsaved_form = True
    actions = ['activate_users', 'deactivate_users']

    @display(description="Пользователь", header=True)
    def display_user_header(self, obj: DataBaseUser) -> Tuple[str, str]:
        """Возвращает ФИО и логин с должностью сотрудника.

        Args:
            obj: Экземпляр DataBaseUser.

        Returns:
            Кортеж (ФИО, логин и должность).
        """
        full_name = f"{obj.last_name} {obj.first_name} {obj.surname}".strip()
        display_name = full_name or obj.username
        subtitle = f"@{obj.username}"
        if obj.title:
            subtitle += f" | {obj.title}"
        return display_name, subtitle

    @display(
        description="Роль",
        label={
            "superuser": "danger",
            "staff": "warning",
            "user": "info",
        },
    )
    def display_role(self, obj: DataBaseUser) -> Tuple[str, str]:
        """Возвращает роль пользователя в системе с бейджем.

        Args:
            obj: Экземпляр DataBaseUser.

        Returns:
            Кортеж (тип роли, наименование).
        """
        if obj.is_superuser:
            return "superuser", "Суперпользователь"
        if obj.is_staff:
            return "staff", "Администратор"
        return "user", "Пользователь"

    @display(
        description="Статус",
        label={
            "active": "success",
            "blocked": "danger",
        },
    )
    def display_status(self, obj: DataBaseUser) -> Tuple[str, str]:
        """Возвращает статус активности пользователя.

        Args:
            obj: Экземпляр DataBaseUser.

        Returns:
            Кортеж (код статуса, наименование).
        """
        if obj.is_active:
            return "active", "Активен"
        return "blocked", "Заблокирован"

    def activate_users(self, request, queryset):
        queryset.update(is_active=True)

    activate_users.short_description = "Активируйте выбранных пользователей"

    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)

    deactivate_users.short_description = "Деактивировать выбранных пользователей"


admin.site.register(DataBaseUser, CustomUserAdmin)

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(Group)
class CustomGroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Административное представление групп и прав доступа."""
    pass


@admin.register(Job)
class JobAdmin(ModelAdmin):
    list_display = ("pk", "name")
    search_fields = ("name",)


@admin.register(AccessLevel)
class AccessLevelAdmin(ModelAdmin):
    pass


@admin.register(DataBaseUserProfile)
class DataBaseUserProfileAdmin(ModelAdmin):
    pass


@admin.register(Citizenships)
class CitizenshipsAdmin(ModelAdmin):
    pass


@admin.register(DataBaseUserWorkProfile)
class DataBaseUserWorkProfileAdmin(ModelAdmin):
    pass


@admin.register(HarmfulWorkingConditions)
class HarmfulWorkingConditionsAdmin(ModelAdmin):
    pass


@admin.register(ViewDocumentsPhysical)
class ViewDocumentsPhysicalAdmin(ModelAdmin):
    pass


@admin.register(HistoryChange)
class HistoryChangeAdmin(ModelAdmin):
    pass


@admin.register(HappyBirthdayGreetings)
class HappyBirthdayGreetingsAdmin(ModelAdmin):
    pass


@admin.register(Affiliation)
class AffiliationAdmin(ModelAdmin):
    pass


@admin.register(VacationScheduleList)
class VacationScheduleListAdmin(ModelAdmin):
    pass


@admin.register(VacationSchedule)
class VacationScheduleAdmin(ModelAdmin):
    pass


@admin.register(IdentityDocuments)
class IdentityDocumentsAdmin(ModelAdmin):
    list_display = ("series", "number", "issued_by_whom", "date_of_issue",
                    "division_code",)  #


@admin.register(CounteragentDocuments)
class CounteragentDocumentsAdmin(ModelAdmin):
    list_display = ("package", "date_of_creation", "description", "document",)  #


# @admin.register(Counteragent)
# class CounteragentAdmin(ModelAdmin):
#     list_display = ("pk", "short_name", "inn", "kpp", "ogrn", "type_counteragent",)
#     search_fields = ("short_name", "inn", "kpp", "ogrn")
#     ordering = ('pk',)

@admin.register(Posts)
class PostsAdmin(ModelAdmin):
    list_display = ("pk", "post_title", "creation_date", "allowed_placed", "email_send", "post_date_start",
                    "post_date_end")
    search_fields = ("post_title", "creation_date")
    ordering = ('-pk',)
    list_filter = ("creation_date", "allowed_placed", "email_send",)


@admin.register(Division)
class DivisionAdmin(ModelAdmin):
    """Администрирование подразделений компании."""
    list_display = ("pk", "code", "name", "display_active")
    search_fields = ("name", "code")
    ordering = ('code',)
    list_filter = ("active",)
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Активно", boolean=True)
    def display_active(self, obj: Division) -> bool:
        """Флаг активности подразделения."""
        return obj.active


@admin.register(UserStats)
class UserStatsAdmin(ModelAdmin):
    list_display = ("pk", "score", "level", "lines_cleared", "games_played")
    ordering = ('created_at',)
    compressed_fields = True


class ApartmentBookingInline(TabularInline):
    model = ApartmentBooking
    extra = 0
    readonly_fields = ['date_created']


@admin.register(Apartments)
class ApartmentsAdmin(ModelAdmin):
    """Администрирование квартир для командированных сотрудников."""
    list_display = ['title', 'place', 'beds_number', 'get_current_occupancy']
    search_fields = ['title', 'place', 'address']
    compressed_fields = True
    warn_unsaved_form = True

    def get_current_occupancy(self, obj):
        from datetime import date
        return obj.get_available_beds(date.today(), date.today())

    get_current_occupancy.short_description = "Свободно мест (сейчас)"


@admin.register(ApartmentBooking)
class ApartmentBookingAdmin(ModelAdmin):
    """
    Админ-класс для модели бронирования квартир с использованием django-unfold.
    """

    # Основные настройки
    list_display = ['display_booking_header', 'display_active', 'process_info']
    list_display_links = ['display_booking_header']
    list_filter = [
        'is_active',
        'apartment',
        ('date_start', RangeDateFilter),
        ('date_end', RangeDateFilter),
    ]
    search_fields = ['apartment__address', 'apartment__title']
    list_per_page = 25
    date_hierarchy = 'date_start'
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Бронирование", header=True)
    def display_booking_header(self, obj: ApartmentBooking) -> Tuple[str, str]:
        """Возвращает заголовок бронирования и период."""
        apt_title = obj.apartment.title if obj.apartment else "Квартира не указана"
        period = f"{obj.date_start} — {obj.date_end}"
        return f"Бронь #{obj.id}", f"{apt_title} ({period})"

    @display(description="Активно", boolean=True)
    def display_active(self, obj: ApartmentBooking) -> bool:
        """Флаг активности бронирования."""
        return obj.is_active

    # Поля для формы редактирования
    fieldsets = [
        ('Информация о бронировании', {
            'fields': ['apartment', 'date_start', 'date_end', 'is_active'],
            'description': 'Укажите квартиру и период бронирования'
        }),
        ('Связанный бизнес-процесс', {
            'fields': ['process_link'],
            'description': 'Бизнес-процесс, связанный с данным бронированием',
            'classes': ['collapse'],
        }),
        ('Системная информация', {
            'fields': ['date_created'],
            'classes': ['collapse'],
        }),
    ]

    # Поля только для чтения
    readonly_fields = ['date_created', 'process_link']

    # Отключаем inlines, так как OneToOneField не поддерживает стандартные inlines
    # Вместо этого используем кастомные методы для отображения связанных данных

    # Действия
    actions = ['activate_bookings', 'deactivate_bookings']

    # Настройки Unfold
    compressed_fields = True
    warn_unsaved_form = True

    def get_queryset(self, request):
        """Оптимизация запросов с select_related для связанных моделей"""
        return super().get_queryset(request).select_related(
            'apartment',
            'process'
        )

    def process_info(self, obj):
        """Отображение информации о бизнес-процессе в списке"""
        if obj.process:
            # Проверяем реальные поля модели ApprovalOficialMemoProcess
            # Замените 'id' на реальные поля, которые есть в модели
            process_id = obj.process.id

            # Пример определения статуса - нужно адаптировать под реальную модель
            # Если в модели есть поле 'status', используйте его:
            # status = getattr(obj.process, 'status', 'Неизвестно')

            # Показываем ID процесса
            return format_html(
                '<a href="{}">Процесс #{}</a>',
                reverse('admin:hrdepartment_app_approvaloficialmemoprocess_change', args=[obj.process.id]),
                process_id
            )
        return "Не привязан"

    process_info.short_description = "Бизнес-процесс"

    def process_link(self, obj):
        """Ссылка на связанный процесс в форме редактирования"""
        if obj.process:
            from django.urls import reverse
            from django.utils.html import format_html

            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                reverse('admin:hrdepartment_app_approvaloficialmemoprocess_change', args=[obj.process.pk]),
                f"Просмотреть процесс #{obj.process.pk}"
            )
        return mark_safe('<span style="color: #666;">Не привязан</span>')

    process_link.short_description = "Бизнес-процесс"

    def activate_bookings(self, request, queryset):
        """Активация выбранных бронирований"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано {updated} бронирований.")

    activate_bookings.short_description = "Активировать выбранные бронирования"

    def deactivate_bookings(self, request, queryset):
        """Деактивация выбранных бронирований"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано {updated} бронирований.")

    deactivate_bookings.short_description = "Деактивировать выбранные бронирования"

    def save_model(self, request, obj, form, change):
        """
        Переопределение save_model для дополнительной логики
        """
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        """
        Динамическое изменение fieldsets в зависимости от наличия объекта
        """
        fieldsets = super().get_fieldsets(request, obj)

        if obj is None:  # При создании нового объекта
            # Убираем process_link, так как процесса ещё нет
            return [
                (title, {'fields': [f for f in data['fields'] if f != 'process_link'],
                         'description': data.get('description', ''),
                         'classes': data.get('classes', [])})
                for title, data in fieldsets
            ]

        return fieldsets

@admin.register(Counteragent)
class CounteragentAdmin(ModelAdmin):
    list_display = ["display_counteragent_header", 'inn', 'kpp', 'type_counteragent', 'duplicates_info', 'related_objects_count']
    list_filter = ['type_counteragent']
    search_fields = ['short_name', 'full_name', 'inn', 'kpp']
    actions = ['find_and_mark_duplicates', 'merge_duplicates']
    ordering = ('pk',)
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Контрагент", header=True)
    def display_counteragent_header(self, obj: Counteragent) -> Tuple[str, str]:
        """Возвращает наименование и реквизиты контрагента."""
        name = obj.short_name or obj.full_name or "Без наименования"
        details = f"ИНН: {obj.inn or '—'}"
        if obj.kpp:
            details += f" | КПП: {obj.kpp}"
        return name, details

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

    def related_objects_count(self, obj):
        """Отображает общее количество связанных объектов"""
        total = 0
        related_fields = self._get_all_related_fields()

        for rel_info in related_fields:
            model = rel_info['model']
            field_name = rel_info['field_name']
            try:
                # Используем exists() для быстрой проверки, если нужно только >0
                # Или count() для точного подсчёта
                count = model.objects.filter(**{field_name: obj}).count()
                total += count
            except Exception:
                continue

        if total > 0:
            return format_html(
                '<a href="{}?{}__id={}" target="_blank" style="color: orange; font-weight: bold;">{} 🔗</a>',
                reverse('admin:customers_app_counteragent_changelist'),
                'related',  # или имя первого связанного поля для фильтрации
                obj.pk,
                total
            )
        return format_html('<span style="color: gray;">0</span>')

    related_objects_count.short_description = "Связи"

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


@admin.register(BiometricConsent)
class BiometricConsentAdmin(ModelAdmin):
    list_display = ['display_consent_header', 'consent_type', 'consent_date', 'display_active', 'scanned_copy_link']
    list_filter = [
        'is_active',
        'consent_type',
        ('consent_date', RangeDateFilter),
    ]
    search_fields = ['consent_number', 'employee__last_name', 'employee__first_name', 'employee_full_name']
    date_hierarchy = 'consent_date'
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Согласие", header=True)
    def display_consent_header(self, obj: BiometricConsent) -> Tuple[str, str]:
        """Возвращает номер согласия и ФИО сотрудника."""
        return f"№ {obj.consent_number or 'б/н'}", obj.employee_full_name

    @display(description="Активно", boolean=True)
    def display_active(self, obj: BiometricConsent) -> bool:
        """Флаг активности согласия."""
        return obj.is_active

    fieldsets = (
        ('Основная информация', {
            'fields': ('employee', 'consent_type', 'consent_number', 'consent_date', )
        }),
        ('Данные сотрудника на момент подписания', {
            'fields': ('employee_full_name', 'employee_position')
        }),
        ('Документ', {
            'fields': ('scanned_copy', 'comment')
        }),
        ('Статус согласия', {
            'fields': ('is_active', 'revocation_date')
        }),
        ('Служебная информация', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def employee_link(self, obj):
        url = reverse('admin:customers_app_databaseuser_change', args=[obj.employee.id])
        return format_html('<a href="{}">{}</a>', url, obj.employee_full_name)

    employee_link.short_description = 'Сотрудник'

    def scanned_copy_link(self, obj):
        if obj.scanned_copy:
            return format_html('<a href="{}" target="_blank">Открыть скан</a>', obj.scanned_copy.url)
        return "Файл не загружен"

    scanned_copy_link.short_description = 'Скан документа'

    def save_model(self, request, obj, form, change):
        if not change:  # при создании
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ConsentType)
class ConsentTypeAdmin(ModelAdmin):
    list_display = ['name', 'code', 'template_link', 'display_active', 'sort_order', 'consents_count']
    list_filter = ['is_active', ('created_at', RangeDateFilter)]
    search_fields = ['name', 'code', 'description']
    list_editable = ['sort_order']
    readonly_fields = ['created_at', 'updated_at']
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Активно", boolean=True)
    def display_active(self, obj: ConsentType) -> bool:
        """Флаг активности типа согласия."""
        return obj.is_active

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Шаблон документа', {
            'fields': ('template',),
            'description': 'Выберите шаблон документа для этого типа согласия'
        }),
        ('Настройки отображения', {
            'fields': ('sort_order',)
        }),
        ('Служебная информация', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def template_link(self, obj):
        if obj.template:
            url = reverse('admin:administration_app_templatedocument_change', args=[obj.template.id])
            return format_html('<a href="{}">{}</a>', url, obj.template.name)
        return "Не указан"

    template_link.short_description = 'Шаблон'

    def consents_count(self, obj):
        count = obj.biometric_consents.count()
        url = reverse('admin:customers_app_biometricconsent_changelist') + f'?consent_type__id={obj.id}'
        return format_html('<a href="{}">{} согласий</a>', url, count)

    consents_count.short_description = 'Используется'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ModelAdmin):
    """Административная панель для управления подписками Web Push устройств."""

    list_display = ("user", "device_info", "created_at", "updated_at")
    search_fields = ("user__username", "user__last_name", "user__first_name", "user_agent", "endpoint")
    list_filter = (("created_at", RangeDateFilter), ("updated_at", RangeDateFilter))
    readonly_fields = ("created_at", "updated_at")
    compressed_fields = True

    def device_info(self, obj):
        """Отображение краткой информации об устройстве."""
        return obj.user_agent[:60] if obj.user_agent else "—"

    device_info.short_description = "Устройство"


@admin.register(UserPasskey)
class UserPasskeyAdmin(ModelAdmin):
    """Административная панель для управления криптографическими ключами доступа Passkey."""

    list_display = ("name", "user", "device_type", "sign_count", "created_at", "last_used_at")
    search_fields = ("name", "user__username", "user__last_name", "user__first_name", "credential_id", "user_agent")
    list_filter = ("device_type", ("created_at", RangeDateFilter), ("last_used_at", RangeDateFilter))
    readonly_fields = ("credential_id", "public_key", "aaguid", "sign_count", "created_at", "last_used_at", "user_agent")
    compressed_fields = True


@admin.register(UserCertificate)
class UserCertificateAdmin(ModelAdmin):
    """Административная панель для управления квалифицированными сертификатами ЭЦП."""

    list_display = ("name", "cn", "user", "snils", "inn", "display_active", "valid_to", "created_at", "last_used_at")
    search_fields = ("name", "cn", "user__username", "user__last_name", "user__first_name", "snils", "inn", "thumbprint", "serial_number", "subject_name")
    list_filter = ("is_active", ("valid_to", RangeDateFilter), ("created_at", RangeDateFilter), ("last_used_at", RangeDateFilter))
    readonly_fields = ("thumbprint", "serial_number", "subject_name", "issuer_name", "snils", "inn", "cn", "valid_from", "valid_to", "certificate_data", "created_at", "last_used_at")
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Активен", boolean=True)
    def display_active(self, obj: UserCertificate) -> bool:
        """Флаг активности сертификата."""
        return obj.is_active


class OrgNodeLeadershipHistoryInline(TabularInline):
    """Встроенная история руководства внутри карточки узла оргструктуры."""

    model = OrgNodeLeadershipHistory
    extra = 1
    autocomplete_fields = ["employee", "job"]
    fields = ("employee", "job", "date_from", "date_to", "is_current", "order_number", "comment")


class OrgStructureNodeInline(TabularInline):
    """Встроенные узлы внутри схемы оргструктуры."""

    model = OrgStructureNode
    extra = 0
    fields = ("custom_name", "division", "node_type", "level", "order", "head_job", "is_active", "pos_x", "pos_y")
    autocomplete_fields = ["division", "head_job"]
    readonly_fields = ("pos_x", "pos_y")
    show_change_link = True


@admin.register(OrgStructure)
class OrgStructureAdmin(ModelAdmin):
    """Административная панель для управления редакциями организационной структуры компании."""

    list_display = ("display_structure_header", "start_date", "end_date", "display_active", "approved_by", "created_at")
    list_filter = ("is_active", ("start_date", RangeDateFilter))
    search_fields = ("title", "version_code", "approved_by", "description")
    readonly_fields = ("created_at", "updated_at")
    inlines = [OrgStructureNodeInline]
    compressed_fields = True
    warn_unsaved_form = True

    @display(description="Оргструктура", header=True)
    def display_structure_header(self, obj: OrgStructure) -> Tuple[str, str]:
        """Возвращает наименование редакции оргструктуры."""
        return obj.title, f"Версия: {obj.version_code or '—'}"

    @display(description="Активна", boolean=True)
    def display_active(self, obj: OrgStructure) -> bool:
        """Флаг активности редакции."""
        return obj.is_active

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "title",
                    "version_code",
                    "is_active",
                    "description",
                )
            },
        ),
        (
            "Ввод в действие и утверждение",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "approved_by",
                    "approval_date",
                )
            },
        ),
        (
            "Конфигурация холста и метаданные",
            {
                "classes": ("collapse",),
                "fields": (
                    "raw_layout_json",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(OrgStructureNode)
class OrgStructureNodeAdmin(ModelAdmin):
    """Административная панель для управления узлами оргструктуры."""

    list_display = (
        "get_title",
        "structure",
        "display_node_type",
        "level",
        "order",
        "head_job",
        "current_leader_display",
        "display_active",
    )
    list_filter = ("structure", "node_type", "is_active")
    search_fields = ("custom_name", "division__name", "head_job__name")
    autocomplete_fields = ["structure", "division", "parent", "head_job"]
    inlines = [OrgNodeLeadershipHistoryInline]
    compressed_fields = True
    warn_unsaved_form = True

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "structure",
                    "custom_name",
                    "division",
                    "parent",
                    "head_job",
                )
            },
        ),
        (
            "Иерархия и тип",
            {
                "fields": (
                    "node_type",
                    "level",
                    "order",
                    "is_active",
                )
            },
        ),
        (
            "Параметры холста",
            {
                "classes": ("collapse",),
                "fields": (
                    "color_scheme",
                    "pos_x",
                    "pos_y",
                ),
            },
        ),
    )

    @display(description="Наименование узла", header=True)
    def get_title(self, obj: OrgStructureNode) -> Tuple[str, str]:
        """Возвращает наименование узла и связанное подразделение.

        Args:
            obj (OrgStructureNode): Экземпляр узла оргструктуры.

        Returns:
            Tuple[str, str]: Кортеж (отображаемое имя узла, наименование подразделения 1С).
        """
        div_name = obj.division.name if obj.division else "Без подразделения 1С"
        return obj.get_display_name(), div_name

    @display(
        description="Тип узла",
        label={
            "TOP_MANAGEMENT": "danger",
            "SERVICE": "primary",
            "DETACHMENT": "info",
            "DIVISION": "secondary",
            "GROUP": "warning",
            "SUBDIVISION": "success",
            "ADVISORY": "primary",
            "ASSISTANT": "info",
        },
    )
    def display_node_type(self, obj: OrgStructureNode) -> Tuple[str, str]:
        """Возвращает тип узла со стилизованным бейджем.

        Args:
            obj (OrgStructureNode): Экземпляр узла оргструктуры.

        Returns:
            Tuple[str, str]: Кортеж (код типа, читаемое название типа).
        """
        return obj.node_type, obj.get_node_type_display()

    @display(description="Активен", boolean=True)
    def display_active(self, obj: OrgStructureNode) -> bool:
        """Возвращает флаг активности узла оргструктуры.

        Args:
            obj (OrgStructureNode): Экземпляр узла оргструктуры.

        Returns:
            bool: True, если узел активен.
        """
        return obj.is_active

    @display(description="Текущий руководитель")
    def current_leader_display(self, obj: OrgStructureNode) -> str:
        """Возвращает строку с текущим действующим руководителем узла.

        Args:
            obj (OrgStructureNode): Экземпляр узла оргструктуры.

        Returns:
            str: ФИО и должность руководителя либо прочерк при отсутствии.
        """
        leader = obj.get_current_leader()
        if leader and leader.employee:
            return f"{leader.employee.title or leader.employee.get_full_name() or leader.employee.username} ({leader.job.name if leader.job else '—'})"
        return "—"


@admin.register(OrgNodeLeadershipHistory)
class OrgNodeLeadershipHistoryAdmin(ModelAdmin):
    """Административная панель для управления историей назначений руководителей."""

    list_display = ("node", "employee", "job", "date_from", "date_to", "display_current", "order_number")
    list_filter = ("is_current", ("date_from", RangeDateFilter), "node__structure")
    search_fields = ("employee__username", "employee__last_name", "employee__first_name", "employee__title", "node__custom_name", "order_number")
    autocomplete_fields = ["node", "employee", "job"]
    readonly_fields = ("created_at",)
    compressed_fields = True
    warn_unsaved_form = True

    fieldsets = (
        (
            "Назначение",
            {
                "fields": (
                    "node",
                    "employee",
                    "job",
                    "is_current",
                )
            },
        ),
        (
            "Период и основание",
            {
                "fields": (
                    "date_from",
                    "date_to",
                    "order_number",
                    "comment",
                    "created_at",
                )
            },
        ),
    )

    @display(description="Текущий", boolean=True)
    def display_current(self, obj: OrgNodeLeadershipHistory) -> bool:
        """Флаг актуального руководства.

        Args:
            obj (OrgNodeLeadershipHistory): Экземпляр истории руководства.

        Returns:
            bool: True, если руководство действует в настоящее время.
        """
        return obj.is_current