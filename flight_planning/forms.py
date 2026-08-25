# flight_planning/forms.py
from datetime import date
from django import forms
from django.utils import timezone
from contracts_app.models import Estate
from hrdepartment_app.models import PlaceProductionActivity
from administration_app.utils import make_custom_field
from .models import AircraftMovement


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
