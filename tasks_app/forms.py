from django import forms

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
        fields = ['user', 'title', 'description', 'completed', 'start_date', 'end_date', 'priority', 'category',
                  'repeat', 'shared_with', 'repeat_interval', 'repeat_days', 'repeat_end_date']
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'shared_with': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.all()
        self.fields['shared_with'].queryset = DataBaseUser.objects.all()
