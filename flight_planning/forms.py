# flight_planning/forms.py
from datetime import date
from django import forms
from django.utils import timezone

from administration_app.utils import make_custom_field
from contracts_app.models import Estate, TypeProperty
from contracts_app.templatetags.custom import FIO_format
from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity

from .models import (
    AircraftMovement,
    PeriodicCheckRecord,
    PeriodicCheckType,
    EmployeeStatusRecord,
    EmployeeStatusType,
)
from .services import get_allowed_staff_queryset, format_short_job



class AircraftMovementForm(forms.ModelForm):
    """
    Форма создания и редактирования записи в журнале перемещения воздушных судов (ВС) по МПД.
    """
    date = forms.DateField(
        label="Дата перемещения",
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control form-control-modern',
                'autocomplete': 'off'
            }
        ),
        input_formats=['%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d', '%d/%m/%Y'],
        required=True
    )

    class Meta:
        model = AircraftMovement
        fields = ['aircraft', 'mpd', 'date', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control form-control-modern',
                'placeholder': 'Укажите основание перемещения, приказ, рейс, служебное примечание...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Настройка выпадающего списка воздушных судов
        self.fields['aircraft'].queryset = Estate.objects.all().select_related('type_property').order_by('registration_number')
        self.fields['aircraft'].label = "Воздушное судно / Борт"
        self.fields['aircraft'].empty_label = "Выберите воздушное судно..."
        self.fields['aircraft'].label_from_instance = lambda obj: (
            f"{obj.registration_number} ({obj.type_property.type_property if obj.type_property else 'ВС'})"
            + (" [ВЫВЕДЕН ИЗ ЭКСПЛУАТАЦИИ]" if obj.is_decommissioned else "")
        )

        # Настройка списка МПД
        self.fields['mpd'].queryset = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')
        self.fields['mpd'].label = "МПД базирования / назначения"
        self.fields['mpd'].empty_label = "Выберите МПД..."

        self.fields['comment'].label = "Основание / Примечание"

        # Дата по умолчанию для новой записи
        if not self.instance.pk and not self.initial.get('date'):
            self.initial['date'] = timezone.now().date()

        for field_name, field in self.fields.items():
            make_custom_field(field)
            if field_name == 'date':
                # Удаляем data-plugin-datepicker для предотвращения конфликта с нативным input type="date"
                field.widget.attrs.pop('data-plugin-datepicker', None)
                field.widget.attrs.pop('data-plugin-options', None)
                field.widget.attrs['type'] = 'date'


class PeriodicCheckRecordForm(forms.ModelForm):
    """Форма добавления и редактирования записи о прохождении периодической проверки сотрудником.

    Attributes:
        start_date (DateField): Дата сдачи/прохождения проверки.
        end_date (DateField): Срок годности/окончания действия проверки.
    """
    start_date = forms.DateField(
        label="Дата прохождения (Начало)",
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control form-control-modern',
                'autocomplete': 'off',
                'id': 'checkStartDateInput'
            }
        ),
        input_formats=['%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d', '%d/%m/%Y'],
        required=True
    )
    end_date = forms.DateField(
        label="Действует до (Окончание)",
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control form-control-modern',
                'autocomplete': 'off',
                'id': 'checkEndDateInput'
            }
        ),
        input_formats=['%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d', '%d/%m/%Y'],
        required=True
    )

    class Meta:
        model = PeriodicCheckRecord
        fields = [
            'employee', 'check_type', 'aircraft_type',
            'start_date', 'end_date', 'document_number',
            'issued_by', 'scan_file', 'notes'
        ]
        widgets = {
            'document_number': forms.TextInput(attrs={
                'class': 'form-control form-control-modern',
                'placeholder': 'Например: Сертификат № 12345, Справка ВЛЭК № 89...'
            }),
            'issued_by': forms.TextInput(attrs={
                'class': 'form-control form-control-modern',
                'placeholder': 'Учебный центр, АУЦ, ВЛЭК, Инструктор...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control form-control-modern',
                'placeholder': 'Дополнительные сведения, результаты, замечания...'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Сотрудники (фильтрация по разрешенным должностям и принадлежности пользователя)
        emp_qs = get_allowed_staff_queryset(user=user)
        if self.instance.pk and getattr(self.instance, 'employee_id', None):
            emp_qs = (emp_qs | DataBaseUser.objects.filter(pk=self.instance.employee_id)).distinct().order_by('last_name', 'first_name')

        self.fields['employee'].queryset = emp_qs
        self.fields['employee'].label = "Сотрудник"
        self.fields['employee'].empty_label = "Выберите сотрудника..."
        self.fields['employee'].label_from_instance = lambda u: (
            f"{FIO_format(u.title or u.username)}" +
            (f" ({format_short_job(u.user_work_profile.job.name)})" if hasattr(u, 'user_work_profile') and u.user_work_profile and u.user_work_profile.job else "")
        )

        # Виды мероприятий
        self.fields['check_type'].queryset = PeriodicCheckType.objects.filter(is_active=True).select_related('aircraft_type').order_by('order', 'name')
        self.fields['check_type'].label = "Вид мероприятия"
        self.fields['check_type'].empty_label = "Выберите вид мероприятия..."
        self.fields['check_type'].label_from_instance = lambda ct: (
            f"{ct.name} [{ct.aircraft_display}] (период: {ct.validity_months} мес.)"
        )

        # Тип ВС
        self.fields['aircraft_type'].queryset = TypeProperty.objects.all().order_by('type_property')
        self.fields['aircraft_type'].label = "Тип ВС"
        self.fields['aircraft_type'].empty_label = "Универсальное (* / Все типы ВС)"
        self.fields['aircraft_type'].required = False

        if not self.instance.pk and not self.initial.get('start_date'):
            self.initial['start_date'] = timezone.now().date()

        for field_name, field in self.fields.items():
            make_custom_field(field)
            if field_name in ('start_date', 'end_date'):
                field.widget.attrs.pop('data-plugin-datepicker', None)
                field.widget.attrs.pop('data-plugin-options', None)
                field.widget.attrs['type'] = 'date'
            if field_name in ('employee', 'check_type', 'aircraft_type'):
                field.widget.attrs.pop('data-plugin-selectTwo', None)
                field.widget.attrs.pop('data-plugin-options', None)
                field.widget.attrs['class'] = 'form-control form-control-modern'
                field.widget.attrs['style'] = 'width: 100%; display: block;'


class PeriodicCheckTypeForm(forms.ModelForm):
    """Форма создания и редактирования вида периодического мероприятия.
    """
    class Meta:
        model = PeriodicCheckType
        fields = [
            'name', 'code', 'aircraft_type', 'validity_months',
            'validity_days', 'applies_to', 'description', 'is_active', 'order'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-modern', 'placeholder': 'Например: Тренажер, ВЛЭК ЛС, КПК на тип ВС'}),
            'code': forms.TextInput(attrs={'class': 'form-control form-control-modern', 'placeholder': 'SIMULATOR, VLEK, CRM...'}),
            'validity_months': forms.NumberInput(attrs={'class': 'form-control form-control-modern', 'min': 1}),
            'validity_days': forms.NumberInput(attrs={'class': 'form-control form-control-modern', 'min': 0}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-modern', 'placeholder': 'Описание мероприятия, ссылка на нормативные документы...'}),
            'order': forms.NumberInput(attrs={'class': 'form-control form-control-modern'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['aircraft_type'].queryset = TypeProperty.objects.all().order_by('type_property')
        self.fields['aircraft_type'].label = "Тип ВС"
        self.fields['aircraft_type'].empty_label = "Универсальное (* / Для всех ВС)"
        self.fields['aircraft_type'].required = False

        for field_name, field in self.fields.items():
            make_custom_field(field)


class EmployeeStatusRecordForm(forms.ModelForm):
    """Форма добавления и редактирования записи о состоянии/статусе сотрудника.

    Attributes:
        start_date (DateField): Дата начала действия состояния (С).
        end_date (DateField): Дата окончания действия состояния (ПО).
    """
    start_date = forms.DateField(
        label="Дата начала (С)",
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control form-control-modern',
                'autocomplete': 'off',
                'id': 'statusStartDateInput'
            }
        ),
        input_formats=['%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d', '%d/%m/%Y'],
        required=True
    )
    end_date = forms.DateField(
        label="Дата окончания (ПО)",
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'form-control form-control-modern',
                'autocomplete': 'off',
                'id': 'statusEndDateInput'
            }
        ),
        input_formats=['%Y-%m-%d', '%d.%m.%Y', '%Y.%m.%d', '%d/%m/%Y'],
        required=True
    )

    class Meta:
        model = EmployeeStatusRecord
        fields = ['employee', 'status_type', 'start_date', 'end_date', 'document_number', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={
                'class': 'form-control form-control-modern',
                'placeholder': 'Номер приказа, больничного листа, распоряжения...'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control form-control-modern',
                'placeholder': 'Укажите комментарии, основания или дополнительную информацию...'
            }),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        emp_qs = get_allowed_staff_queryset(user=user)
        if self.instance.pk and getattr(self.instance, 'employee_id', None):
            emp_qs = (emp_qs | DataBaseUser.objects.filter(pk=self.instance.employee_id)).distinct().order_by('last_name', 'first_name')

        self.fields['employee'].queryset = emp_qs
        self.fields['employee'].label_from_instance = lambda u: (
            f"{FIO_format(u.title or (u.last_name + ' ' + u.first_name).strip() or u.username)}"
            + (f" ({format_short_job(u.user_work_profile.job.name)})" if hasattr(u, 'user_work_profile') and u.user_work_profile and u.user_work_profile.job else "")
        )
        self.fields['employee'].empty_label = "Выберите сотрудника..."

        self.fields['status_type'].queryset = EmployeeStatusType.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['status_type'].empty_label = "Выберите вид состояния..."

        if not self.instance.pk and not self.initial.get('start_date'):
            self.initial['start_date'] = timezone.now().date()
        if not self.instance.pk and not self.initial.get('end_date'):
            self.initial['end_date'] = timezone.now().date()

        for field_name, field in self.fields.items():
            make_custom_field(field)
            if field_name in ('start_date', 'end_date'):
                field.widget.attrs.pop('data-plugin-datepicker', None)
                field.widget.attrs.pop('data-plugin-options', None)
                field.widget.attrs['type'] = 'date'
            if field_name in ('employee', 'status_type'):
                field.widget.attrs.pop('data-plugin-selectTwo', None)
                field.widget.attrs.pop('data-plugin-options', None)
                field.widget.attrs['class'] = 'form-control form-control-modern'
                field.widget.attrs['style'] = 'width: 100%; display: block;'


class EmployeeStatusTypeForm(forms.ModelForm):
    """Форма создания и редактирования вида состояния сотрудника."""

    class Meta:
        model = EmployeeStatusType
        fields = ['name', 'code', 'color', 'is_blocking', 'order', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-modern', 'placeholder': 'Например: Отпуск, Больничный, Резерв'}),
            'code': forms.Select(attrs={'class': 'form-control form-control-modern'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color form-control-modern', 'style': 'height: 42px;'}),
            'order': forms.NumberInput(attrs={'class': 'form-control form-control-modern', 'min': 1}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control form-control-modern', 'placeholder': 'Краткое описание регламента или условий...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            make_custom_field(field)
            if field_name == 'color':
                field.widget.attrs.pop('data-plugin-colorpicker', None)
                field.widget.attrs['type'] = 'color'


