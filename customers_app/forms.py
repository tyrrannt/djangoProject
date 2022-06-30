from django.contrib.auth.forms import AuthenticationForm
from .models import DataBaseUser


class DataBaseUserLoginForm(AuthenticationForm):
    class Meta:
        model = DataBaseUser
        fields = ('username', 'password')

    def __init__(self, *args, **kwargs):
        super(DataBaseUserLoginForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
