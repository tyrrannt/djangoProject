from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import DataBaseUser
from django import forms


class DataBaseUserLoginForm(AuthenticationForm):
    class Meta:
        model = DataBaseUser
        fields = ('username', 'password')

    def __init__(self, *args, **kwargs):
        super(DataBaseUserLoginForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class DataBaseUserRegisterForm(UserCreationForm):
    class Meta:
        model = DataBaseUser
        fields = ('username', 'password1', 'password2', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields['first_name'].required = True
        # self.fields['last_name'].required = True
        self.fields['email'].required = True
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            # field.help_text = ''


class DataBaseUserUpdateForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            'username', 'first_name', 'last_name', 'email', 'birthday', 'password', 'avatar', 'access_right', 'address',
            'type_users', 'phone', 'corp_phone', 'works', 'gender', 'surname')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            field.help_text = ''
            if field_name == 'password':
                field.widget = forms.HiddenInput()


class UserEditForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = ('username', 'first_name', 'last_name', 'email', 'birthday', 'password', 'avatar')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            field.help_text = ''
            if field_name == 'password':
                field.widget = forms.HiddenInput()


class UserProfileForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            'username', 'first_name', 'last_name', 'surname', 'access_right', 'address', 'type_users', 'phone', 'email',
            'birthday', 'password', 'avatar')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
