from django import forms

from administration_app.utils import make_custom_field
from customers_app.models import DataBaseUser
from .models import Task, Category


class TaskForm(forms.ModelForm):
    repeat_days = forms.MultipleChoiceField(
        choices=[
            ('0', 'Понедельник'),
            ('1', 'Вторник'),
            ('2', 'Среда'),
            ('3', 'Четверг'),
            ('4', 'Пятница'),
            ('5', 'Суббота'),
            ('6', 'Воскресенье'),
        ],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Task
        exclude = ['user']
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'shared_with': forms.SelectMultiple(attrs={
                'class': 'form-control',
                'id': 'id_shared_with',
                'multiple': 'multiple',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['shared_with'].queryset = DataBaseUser.objects.filter(is_active=True).order_by('last_name')
        self.fields['shared_with'].label = "Пользователи с доступом"
        self.fields['shared_with'].help_text = "Выберите пользователей, которые смогут видеть эту задачу"
        # for field in self.fields:
        #     make_custom_field(self.fields[field])

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'Дата завершения не может быть раньше даты начала.')
        return cleaned_data
