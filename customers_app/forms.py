from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import DataBaseUser, Posts, Counteragent, UserAccessMode, Division, Job
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
        fields = ('username', 'password1', 'password2', 'email', 'first_name', 'last_name',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            # field.help_text = ''


class DataBaseUserUpdateForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            # 'type_users', 'phone', 'works', 'gender', 'surname'
            'last_name', 'first_name', 'surname', 'email', 'birthday', 'internal_phone', 'work_phone',
            'personal_phone', 'avatar', 'address', 'access_level',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            field.help_text = ''
            if field_name == 'password':
                field.widget = forms.HiddenInput()


class DataBaseUserAddForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            #  'first_name', 'last_name', 'email', 'birthday',  'access_right',
            'last_name', 'first_name', 'surname', 'email', 'birthday', 'internal_phone', 'work_phone',
            'personal_phone', 'avatar', 'address', 'access_level', 'username', 'type_users',
            'password', 'job', 'divisions'
        )


class PostsAddForm(forms.ModelForm):
    class Meta:
        model = Posts
        fields = ('post_description', 'post_divisions', 'allowed_placed')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            field.help_text = ''


class CounteragentUpdateForm(forms.ModelForm):
    class Meta:
        model = Counteragent
        fields = ('short_name', 'full_name', 'inn', 'kpp', 'type_counteragent',
                  'juridical_address', 'physical_address', 'email', 'phone',
                  'director', 'accountant', 'contact_person')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class CounteragentAddForm(forms.ModelForm):
    class Meta:
        model = Counteragent
        fields = ('short_name', 'full_name', 'inn', 'kpp', 'type_counteragent',
                  'juridical_address', 'physical_address', 'email', 'phone',
                  'director', 'accountant', 'contact_person')


class DivisionsAddForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ('parent_category', 'name', 'description', 'history')


class DivisionsUpdateForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ('parent_category', 'name', 'description', 'active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class JobsAddForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ('code', 'name')


class JobsUpdateForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ('code', 'name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            #  'phone', 'works', 'access_level', 'avatar', 'surname'
            'last_name', 'first_name', 'surname', 'email', 'birthday', 'internal_phone', 'work_phone',
            'personal_phone', 'address', 'gender', 'type_users', 'divisions', 'job',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''
