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
            'last_name', 'first_name', 'surname', 'email', 'birthday',
            'personal_phone', 'avatar', 'address', 'access_level', 'user_profile', 'user_work_profile',
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
            'last_name', 'first_name', 'surname', 'email', 'birthday',
            'personal_phone', 'avatar', 'address', 'access_level', 'username', 'type_users',
            'password', 'user_profile', 'user_work_profile',
        )


class PostsAddForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
    post_divisions.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    class Meta:
        model = Posts
        fields = ('post_description', 'post_divisions', 'allowed_placed', 'responsible')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'
            field.help_text = ''


class PostsUpdateForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
    post_divisions.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    post_date_start = forms.DateField(required=False)
    post_date_start.widget.attrs.update(
        {'class': 'form-control form-control-modern'})
    post_date_end = forms.DateField(required=False)
    post_date_end.widget.attrs.update(
        {'class': 'form-control form-control-modern'})

    class Meta:
        model = Posts
        fields = ('post_description', 'post_divisions', 'allowed_placed', 'post_date_start', 'post_date_end')

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
                  'director', 'accountant', 'contact_person', 'ogrn')

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
                  'director', 'accountant', 'contact_person', 'ogrn')


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
        fields = ('code', 'name', 'harmful', 'ref_key', 'excluded_standard_spelling', 'right_to_approval')


class JobsUpdateForm(forms.ModelForm):

    class Meta:
        model = Job
        fields = ('code', 'name', 'harmful', 'ref_key', 'excluded_standard_spelling', 'right_to_approval')


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            #  'phone', 'works', 'access_level', 'avatar', 'surname'
            'last_name', 'first_name', 'surname', 'email', 'birthday',
            'personal_phone', 'address', 'gender', 'type_users',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''
