from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

class CreateRoomForm(forms.Form):
    room_name = forms.CharField(
        max_length=100, 
        label="Название комнаты",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: Совещание по проекту'})
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True),
        label="Пригласить участников",
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2'})
    )
