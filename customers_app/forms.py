import hashlib

from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError

from .models import DataBaseUser, Posts, Counteragent, Division, Job, Groups, HarmfulWorkingConditions
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
            'personal_phone', 'avatar', 'address', 'user_profile', 'user_work_profile',
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
            'personal_phone', 'avatar', 'address', 'username', 'type_users',
            'password', 'user_profile', 'user_work_profile',
        )


class PostsAddForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).order_by('code'))
    post_date_start = forms.DateField(required=False)
    post_date_end = forms.DateField(required=False)

    class Meta:
        model = Posts
        fields = ('post_description', 'post_divisions', 'allowed_placed', 'responsible',
                  'post_date_start', 'post_date_end')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        super(PostsAddForm, self).__init__(*args, **kwargs)
        self.fields['post_description'].widget.attrs.update({'class': 'form-control django_ckeditor_5'})
        self.fields['post_description'].required = False
        self.fields['post_divisions'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-multiselect': True, 'multiple': 'multiple',
             'data-plugin-options': '{ "maxHeight": 200, "includeSelectAllOption": true }'})

    def clean(self):
        clean_data = super().clean()
        start_date = clean_data.get('post_date_start')
        end_date = clean_data.get('post_date_end')
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError('Дата окончания не может быть меньше даты начала!')

    # def clean_post_description(self):
    #     clean_data = self.cleaned_data['post_description']
    #     if clean_data == '':
    #         raise ValidationError('Сообщение не может быть пустым!')


class PostsUpdateForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
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
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        super(PostsUpdateForm, self).__init__(*args, **kwargs)
        self.fields['post_description'].widget.attrs.update({'class': 'form-control django_ckeditor_5'})
        self.fields['post_description'].required = False
        self.fields['post_divisions'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-multiselect': True, 'multiple': 'multiple',
             'data-plugin-options': '{ "maxHeight": 200, "includeSelectAllOption": true }'})

    def clean(self):
        clean_data = super().clean()
        start_date = clean_data.get('post_date_start')
        end_date = clean_data.get('post_date_end')
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError('Дата окончания не может быть меньше даты начала!')
    # def clean_post_description(self):
    #     clean_data = self.cleaned_data['post_description']
    #     if clean_data == '':
    #         raise ValidationError('Сообщение не может быть пустым!')


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
    parent_category = forms.ModelChoiceField(queryset=Division.objects.all(), required=False)
    parent_category.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Division
        fields = ('parent_category', 'name', 'description', 'history', 'address', 'active', 'destination_point',
                  'type_of_role')


class DivisionsUpdateForm(forms.ModelForm):
    type_of_role = forms.ChoiceField(choices=Division.type_of)
    type_of_role.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    parent_category = forms.ModelChoiceField(queryset=Division.objects.all(), required=False)
    parent_category.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Division
        fields = ('parent_category', 'name', 'description', 'address', 'active', 'destination_point', 'type_of_role',
                  )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class JobsAddForm(forms.ModelForm):
    group = forms.ModelMultipleChoiceField(queryset=Groups.objects.all())
    group.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    harmful = forms.ModelMultipleChoiceField(queryset=HarmfulWorkingConditions.objects.all(), required=False)
    harmful.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Job
        fields = ('code', 'name', 'harmful', 'ref_key', 'excluded_standard_spelling', 'right_to_approval', 'group')


class JobsUpdateForm(forms.ModelForm):
    type_of_job = forms.ChoiceField(choices=Job.job_type)
    type_of_job.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    group = forms.ModelMultipleChoiceField(queryset=Groups.objects.all(), required=False)
    group.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    harmful = forms.ModelMultipleChoiceField(queryset=HarmfulWorkingConditions.objects.all(), required=False)
    harmful.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Job
        fields = ('code', 'name', 'harmful', 'ref_key', 'excluded_standard_spelling', 'right_to_approval',
                  'type_of_job', 'group')


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            #  'phone', 'works', 'access_level',  'surname'
            'last_name', 'first_name', 'surname', 'email', 'birthday',
            'personal_phone', 'address', 'gender', 'type_users', 'avatar',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class ChangeAvatarUpdateForm(forms.ModelForm):
    class Meta:
        model = DataBaseUser
        fields = ('avatar',)


class ChangePassPraseUpdateForm(forms.ModelForm):
    passphrase = forms.CharField(label='Кодовое слово')
    passphrase2 = forms.CharField(label='Кодовое слово (повторно)')

    class Meta:
        model = DataBaseUser
        fields = ('passphrase',)

    def clean(self):
        cleaned_data = super().clean()
        passphrase_first = cleaned_data.get("passphrase")
        passphrase_second = cleaned_data.get("passphrase2")
        if passphrase_first != passphrase_second:
            raise ValidationError("Кодовые слова не совпадают!")

    def clean_passphrase(self):
        cleaned_data = self.cleaned_data['passphrase']
        if cleaned_data != '':
            cleaned_data = hashlib.sha256(cleaned_data.encode()).hexdigest()
        return cleaned_data

    def clean_passphrase2(self):
        cleaned_data = self.cleaned_data['passphrase2']
        if cleaned_data != '':
            cleaned_data = hashlib.sha256(cleaned_data.encode()).hexdigest()
        return cleaned_data


class GroupAddForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all())
    permissions.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Groups
        fields = ('name', 'permissions')


class GroupUpdateForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all())
    permissions.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Groups
        fields = ('name', 'permissions')
