import hashlib

from django.contrib.auth.forms import (
    AuthenticationForm,
    UserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db.models import Q
from django_ckeditor_5.widgets import CKEditor5Widget

from administration_app.utils import make_custom_field
from .models import (
    DataBaseUser,
    Posts,
    Counteragent,
    Division,
    Job,
    Groups,
    HarmfulWorkingConditions,
    AccessLevel,
    Affiliation, CounteragentDocuments, BiometricConsent,
)
from contracts_app.models import TypeProperty
from django import forms


class DataBaseUserLoginForm(AuthenticationForm):
    class Meta:
        model = DataBaseUser
        fields = ("username", "password")

    def __init__(self, *args, **kwargs):
        super(DataBaseUserLoginForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"


class DataBaseUserRegisterForm(UserCreationForm):
    class Meta:
        model = DataBaseUser
        fields = (
            "username",
            "password1",
            "password2",
            "email",
            "first_name",
            "last_name",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control mb-4"
            # field.help_text = ''


class DataBaseUserUpdateForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            # 'type_users', 'phone', 'works', 'gender', 'surname'
            "last_name",
            "first_name",
            "surname",
            "email",
            "birthday",
            "personal_phone",
            "avatar",
            "address",
            "user_profile",
            "user_work_profile",
            "type_of_role"
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control mb-4"
            field.help_text = ""
            if field_name == "password":
                field.widget = forms.HiddenInput()


class DataBaseUserAddForm(UserChangeForm):
    class Meta:
        model = DataBaseUser
        fields = (
            #  'first_name', 'last_name', 'email', 'birthday',  'access_right',
            "last_name",
            "first_name",
            "surname",
            "email",
            "birthday",
            "personal_phone",
            "avatar",
            "address",
            "username",
            "type_users",
            "password",
            "user_profile",
            "user_work_profile",
        )


class PostsAddForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(
        queryset=Division.objects.filter(active=True).order_by("code")
    )
    post_date_start = forms.DateField(required=False)
    post_date_end = forms.DateField(required=False)

    class Meta:
        model = Posts
        fields = (
            "post_description",
            "post_divisions",
            "allowed_placed",
            "responsible",
            "post_date_start",
            "post_date_end",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        super(PostsAddForm, self).__init__(*args, **kwargs)
        self.fields["post_description"].widget.attrs.update(
            {"class": "form-control django_ckeditor_5"}
        )
        self.fields["post_description"].required = False
        self.fields["post_divisions"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )

    def clean(self):
        clean_data = super().clean()
        start_date = clean_data.get("post_date_start")
        end_date = clean_data.get("post_date_end")
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError(
                    "Дата окончания не может быть меньше даты начала!"
                )

    # def clean_post_description(self):
    #     clean_data = self.cleaned_data['post_description']
    #     if clean_data == '':
    #         raise ValidationError('Сообщение не может быть пустым!')


class PostsUpdateForm(forms.ModelForm):
    post_divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
    post_date_start = forms.DateField(required=False)
    post_date_start.widget.attrs.update({"class": "form-control form-control-modern"})
    post_date_end = forms.DateField(required=False)
    post_date_end.widget.attrs.update({"class": "form-control form-control-modern"})

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        super(PostsUpdateForm, self).__init__(*args, **kwargs)
        self.fields["post_description"].required = False
        self.fields["post_divisions"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )

    class Meta:
        model = Posts
        fields = (
            "post_title",
            "post_description",
            "post_divisions",
            "allowed_placed",
            "post_date_start",
            "post_date_end",
        )
        widgets = {
            "post_description": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"}, config_name="extends"
            )
        }

    def clean(self):
        clean_data = super().clean()
        start_date = clean_data.get("post_date_start")
        end_date = clean_data.get("post_date_end")
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError(
                    "Дата окончания не может быть меньше даты начала!"
                )

    # def clean_post_description(self):
    #     clean_data = self.cleaned_data['post_description']
    #     if clean_data == '':
    #         raise ValidationError('Сообщение не может быть пустым!')


class CounteragentUpdateForm(forms.ModelForm):
    class Meta:
        model = Counteragent
        fields = (
            "short_name",
            "full_name",
            "inn",
            "kpp",
            "type_counteragent",
            "juridical_address",
            "physical_address",
            "email",
            "phone",
            "director",
            "accountant",
            "contact_person",
            "ogrn",
            "natural_person",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control form-control-modern"
            field.help_text = ""


class CounteragentAddForm(forms.ModelForm):
    class Meta:
        model = Counteragent
        fields = (
            "short_name",
            "full_name",
            "inn",
            "kpp",
            "type_counteragent",
            "juridical_address",
            "physical_address",
            "email",
            "phone",
            "director",
            "accountant",
            "contact_person",
            "ogrn",
            "natural_person",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class DivisionsAddForm(forms.ModelForm):
    parent_category = forms.ModelChoiceField(
        queryset=Division.objects.all(), required=False
    )
    parent_category.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Division
        fields = (
            "parent_category",
            "name",
            "description",
            "history",
            "address",
            "active",
            "destination_point",
            "type_of_role",
        )


class DivisionsUpdateForm(forms.ModelForm):
    type_of_role = forms.ChoiceField(choices=Division.type_of)
    type_of_role.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    parent_category = forms.ModelChoiceField(
        queryset=Division.objects.all(), required=False
    )
    parent_category.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Division
        fields = (
            "parent_category",
            "name",
            "description",
            "address",
            "active",
            "destination_point",
            "type_of_role",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control form-control-modern"
            field.help_text = ""


class JobsAddForm(forms.ModelForm):
    """Форма добавления новой должности."""

    name = forms.CharField(
        label="Наименование должности",
        max_length=200,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern",
                "placeholder": "Введите наименование должности...",
            }
        ),
    )
    code = forms.CharField(
        label="Номер по ОК (ОКПДТР)",
        max_length=5,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern",
                "placeholder": "Код ОКПДТР (напр. 26541)",
            }
        ),
    )
    ref_key = forms.CharField(
        label="Уникальный номер (1С GUID)",
        max_length=37,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern font-monospace",
                "placeholder": "00000000-0000-0000-0000-000000000000",
            }
        ),
    )
    employment_function = forms.CharField(
        label="Трудовая функция (1С GUID)",
        max_length=37,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern font-monospace",
                "placeholder": "00000000-0000-0000-0000-000000000000",
            }
        ),
    )
    type_of_job = forms.ChoiceField(
        label="Принадлежность к составу",
        choices=Job.job_type,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-control form-control-modern",
            }
        ),
    )
    division_affiliation = forms.ModelChoiceField(
        label="Подразделение",
        queryset=Affiliation.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    group = forms.ModelMultipleChoiceField(
        label="Группы должности",
        queryset=Groups.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    harmful = forms.ModelMultipleChoiceField(
        label="Вредные условия труда",
        queryset=HarmfulWorkingConditions.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    right_to_approval = forms.BooleanField(
        label="Имеет право на согласование",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "role": "switch",
            }
        ),
    )
    excluded_standard_spelling = forms.BooleanField(
        label="Исключена из штатного расписания",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "role": "switch",
            }
        ),
    )

    class Meta:
        model = Job
        fields = (
            "name",
            "code",
            "ref_key",
            "employment_function",
            "type_of_job",
            "division_affiliation",
            "harmful",
            "group",
            "right_to_approval",
            "excluded_standard_spelling",
        )

    def __init__(self, *args, **kwargs):
        """Инициализация формы с настройкой виджетов."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class JobsUpdateForm(forms.ModelForm):
    """Форма редактирования существующей должности."""

    name = forms.CharField(
        label="Наименование должности",
        max_length=200,
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern",
                "placeholder": "Введите наименование должности...",
            }
        ),
    )
    code = forms.CharField(
        label="Номер по ОК (ОКПДТР)",
        max_length=5,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern",
                "placeholder": "Код ОКПДТР (напр. 26541)",
            }
        ),
    )
    ref_key = forms.CharField(
        label="Уникальный номер (1С GUID)",
        max_length=37,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern font-monospace",
                "placeholder": "00000000-0000-0000-0000-000000000000",
            }
        ),
    )
    employment_function = forms.CharField(
        label="Трудовая функция (1С GUID)",
        max_length=37,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-modern font-monospace",
                "placeholder": "00000000-0000-0000-0000-000000000000",
            }
        ),
    )
    type_of_job = forms.ChoiceField(
        label="Принадлежность к составу",
        choices=Job.job_type,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-control form-control-modern",
            }
        ),
    )
    division_affiliation = forms.ModelChoiceField(
        label="Подразделение",
        queryset=Affiliation.objects.all(),
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    group = forms.ModelMultipleChoiceField(
        label="Группы должности",
        queryset=Groups.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    harmful = forms.ModelMultipleChoiceField(
        label="Вредные условия труда",
        queryset=HarmfulWorkingConditions.objects.all(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
            }
        ),
    )
    right_to_approval = forms.BooleanField(
        label="Имеет право на согласование",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "role": "switch",
            }
        ),
    )
    excluded_standard_spelling = forms.BooleanField(
        label="Исключена из штатного расписания",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "role": "switch",
            }
        ),
    )

    class Meta:
        model = Job
        fields = (
            "name",
            "code",
            "ref_key",
            "employment_function",
            "type_of_job",
            "division_affiliation",
            "harmful",
            "group",
            "right_to_approval",
            "excluded_standard_spelling",
        )

    def __init__(self, *args, **kwargs):
        """Инициализация формы с настройкой виджетов."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class StaffUpdateForm(forms.ModelForm):
    """Форма редактирования учетной записи сотрудника на портале.

    Позволяет изменять персональные данные, контактную информацию,
    права доступа, а также квалификационные данные подтверждающего
    персонала ТО ВС (ФАП-145 / ФАП-147) без обращения к панели администратора.

    Attributes:
        user_access (ModelChoiceField): Уровень доступа пользователя.
        allowed_aircraft_types (ModelMultipleChoiceField): Множественный выбор типов ВС
            согласно квалификационным отметкам свидетельства специалиста по ТО.
    """

    user_access = forms.ModelChoiceField(
        queryset=AccessLevel.objects.all(), required=False, label="Права доступа"
    )
    user_access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    allowed_aircraft_types = forms.ModelMultipleChoiceField(
        queryset=TypeProperty.objects.all().order_by("type_property"),
        required=False,
        label="Типы ВС по свидетельству специалиста",
        help_text="Типы воздушных судов, указанные в свидетельстве специалиста по ТО ВС.",
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control form-control-modern",
                "data-plugin-selectTwo": True,
                "multiple": "multiple",
                "data-plugin-options": '{"placeholder": "Выберите типы ВС...", "allowClear": true, "width": "100%"}',
            }
        ),
    )

    class Meta:
        model = DataBaseUser
        fields = (
            # 'username', 'first_name', 'last_name', 'email', 'birthday', 'password',  'access_right',
            #  'phone', 'works', 'access_level',  'surname'
            "last_name",
            "first_name",
            "surname",
            "email",
            "birthday",
            "user_access",
            "is_active",
            "personal_phone",
            "address",
            "gender",
            "type_users",
            "avatar",
            "is_staff",
            "is_superuser",
            "type_of_role",
            "maintenance_staff_certificate",
            "allowed_aircraft_types",
        )

    def __init__(self, *args, **kwargs):
        """Инициализирует виджеты и параметры полей формы сотрудника.

        Настраивает стилизацию Porto Admin для полей формы, переключатели iOS-switch
        для булевых атрибутов и Select2-виджет для разрешенных типов воздушных судов.

        Args:
            *args: Позиционные аргументы родительского конструктора ModelForm.
            **kwargs: Именованные аргументы родительского конструктора ModelForm.
        """
        super(StaffUpdateForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control form-control-modern"
            field.help_text = ""
        self.fields["is_active"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["is_staff"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["is_superuser"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        if "allowed_aircraft_types" in self.fields:
            self.fields["allowed_aircraft_types"].widget.attrs.update(
                {
                    "class": "form-control form-control-modern",
                    "data-plugin-selectTwo": True,
                    "multiple": "multiple",
                    "data-plugin-options": '{"placeholder": "Выберите типы ВС...", "allowClear": true, "width": "100%"}',
                }
            )
        if "maintenance_staff_certificate" in self.fields:
            self.fields["maintenance_staff_certificate"].widget.attrs.update(
                {
                    "class": "form-control form-control-modern",
                    "placeholder": "например, III. № 1234567",
                }
            )


class ChangeAvatarUpdateForm(forms.ModelForm):
    class Meta:
        model = DataBaseUser
        fields = ("avatar",)


class ChangePassPraseUpdateForm(forms.ModelForm):
    passphrase = forms.CharField(label="Кодовое слово")
    passphrase2 = forms.CharField(label="Кодовое слово (повторно)")

    class Meta:
        model = DataBaseUser
        fields = ("passphrase",)

    def clean(self):
        cleaned_data = super().clean()
        passphrase_first = cleaned_data.get("passphrase")
        passphrase_second = cleaned_data.get("passphrase2")
        if passphrase_first != passphrase_second:
            raise ValidationError("Кодовые слова не совпадают!")

    def clean_passphrase(self):
        cleaned_data = self.cleaned_data["passphrase"]
        if cleaned_data != "":
            cleaned_data = hashlib.sha256(cleaned_data.encode()).hexdigest()
        return cleaned_data

    def clean_passphrase2(self):
        cleaned_data = self.cleaned_data["passphrase2"]
        if cleaned_data != "":
            cleaned_data = hashlib.sha256(cleaned_data.encode()).hexdigest()
        return cleaned_data


class GroupAddForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all(), label='Права доступа')

    class Meta:
        model = Groups
        fields = ("name", "permissions")

    def __init__(self, *args, **kwargs):
        super(GroupAddForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class GroupUpdateForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all(), label='Права доступа')

    class Meta:
        model = Groups
        fields = ("name", "permissions")

    def __init__(self, *args, **kwargs):
        super(GroupUpdateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class CounteragentDocumentsAddForm(forms.ModelForm):
    description = forms.CharField(required=False)

    class Meta:
        model = CounteragentDocuments
        fields = ('document', 'description', 'package')

    def __init__(self, *args, **kwargs):
        super(CounteragentDocumentsAddForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class CounteragentDocumentsUpdateForm(forms.ModelForm):
    class Meta:
        model = CounteragentDocuments
        fields = ('document', 'description', 'package')

    def __init__(self, *args, **kwargs):
        super(CounteragentDocumentsUpdateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class BiometricConsentForm(forms.ModelForm):
    """Форма создания и редактирования согласия / кадрового документа сотрудника."""

    class Meta:
        model = BiometricConsent
        fields = [
            'employee',
            'consent_type',
            'consent_number',
            'consent_date',
            'signer',
            'powers_of_attorney',
            'employment_contract_number',
            'employment_contract_date',
            'employee_full_name',
            'employee_position',
            'comment',
            'scanned_copy',
            'is_active',
            'revocation_date',
        ]

    def __init__(self, *args, **kwargs):
        """Инициализирует поля формы, виджеты и списки подписантов и доверенностей."""
        super().__init__(*args, **kwargs)
        from customers_app.models import ConsentType, DocumentSigner
        from hrdepartment_app.models import PowerOfAttorney

        for field in self.fields:
            make_custom_field(self.fields[field])

        # поля которые не обязательны при валидации формы
        self.fields['comment'].required = False
        self.fields['consent_number'].required = False
        self.fields['employee_full_name'].required = False
        self.fields['employee_position'].required = False
        self.fields['scanned_copy'].required = False
        self.fields['revocation_date'].required = False
        self.fields['signer'].required = False
        self.fields['powers_of_attorney'].required = False
        self.fields['employment_contract_number'].required = False
        self.fields['employment_contract_date'].required = False

        self.fields['consent_type'].queryset = ConsentType.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['signer'].queryset = DocumentSigner.objects.filter(is_active=True).order_by('-is_default', 'sort_order', 'short_name')
        self.fields['powers_of_attorney'].queryset = PowerOfAttorney.objects.filter(
            cancellation_date__isnull=True
        ).order_by('-issue_date', '-number')
        self.fields['powers_of_attorney'].widget.attrs.update({
            'class': 'form-select',
            'size': '4',
        })

        # Ограничиваем выбор только активными пользователями
        if self.instance.pk:
            self.fields['employee'].queryset = DataBaseUser.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.employee_id)
            )
        else:
            self.fields['employee'].queryset = DataBaseUser.objects.filter(is_active=True)
            default_signer = DocumentSigner.objects.filter(is_active=True, is_default=True).first()
            if default_signer and not self.initial.get('signer'):
                self.initial['signer'] = default_signer

        # Если это редактирование, блокируем изменение сотрудника
        if self.instance and self.instance.pk:
            self.fields['employee'].widget.attrs['readonly'] = True
            self.fields['consent_number'].widget.attrs['readonly'] = True

    def clean(self):
        """Валидирует обязательность подписанта и доверенности(ей) для договоров и соглашений."""
        cleaned_data = super().clean()
        consent_type = cleaned_data.get('consent_type')
        signer = cleaned_data.get('signer')
        poas = cleaned_data.get('powers_of_attorney')

        if consent_type and consent_type.requires_signer:
            if not signer:
                self.add_error(
                    'signer',
                    'Для выбранного типа документа необходимо указать подписанта от работодателя.'
                )
            elif not signer.acts_by_charter and (not poas or len(poas) == 0):
                self.add_error(
                    'powers_of_attorney',
                    f'Подписант {signer.short_name} действует по доверенности — выберите одну или несколько доверенностей из реестра.'
                )
        elif signer and not signer.acts_by_charter and (not poas or len(poas) == 0):
            self.add_error(
                'powers_of_attorney',
                f'При указании подписанта {signer.short_name} необходимо выбрать доверенность(и), на основании которых он действует.'
            )

        return cleaned_data


class HirePackageForm(forms.Form):
    """Форма пакетного формирования документов при приёме сотрудника на работу (ZIP)."""

    employee = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by('last_name', 'first_name'),
        label="Сотрудник",
    )
    consent_date = forms.DateField(
        label="Дата подписания документов",
        input_formats=["%d.%m.%Y", "%Y-%m-%d"],
    )
    employment_contract_number = forms.CharField(
        label="Номер трудового договора",
        max_length=50,
        required=False,
        help_text="Если оставить пустым — подставится из карточки сотрудника.",
    )
    employment_contract_date = forms.DateField(
        label="Дата трудового договора",
        required=False,
        input_formats=["%d.%m.%Y", "%Y-%m-%d"],
        help_text="Если оставить пустым — подставится из карточки сотрудника или даты подписания.",
    )
    consent_types = forms.ModelMultipleChoiceField(
        queryset=None,
        label="Документы для включения в пакет",
        widget=forms.CheckboxSelectMultiple,
    )
    signer = forms.ModelChoiceField(
        queryset=None,
        label="Подписант от работодателя (для договора и соглашения)",
        required=False,
    )
    powers_of_attorney = forms.ModelMultipleChoiceField(
        queryset=None,
        label="Доверенность(и) подписанта",
        required=False,
        help_text="Удерживайте Ctrl для выбора нескольких доверенностей.",
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        """Настраивает актуальные выборки типов документов, подписантов и доверенностей."""
        super().__init__(*args, **kwargs)
        from customers_app.models import ConsentType, DocumentSigner
        from hrdepartment_app.models import PowerOfAttorney

        self.fields['consent_types'].queryset = ConsentType.objects.filter(is_active=True).order_by('sort_order', 'name')
        self.fields['signer'].queryset = DocumentSigner.objects.filter(is_active=True).order_by('-is_default', 'sort_order', 'short_name')
        self.fields['powers_of_attorney'].queryset = PowerOfAttorney.objects.filter(
            cancellation_date__isnull=True
        ).order_by('-issue_date', '-number')

        for fname in ('employee', 'consent_date', 'employment_contract_number', 'employment_contract_date', 'signer'):
            make_custom_field(self.fields[fname])

        self.fields['powers_of_attorney'].widget.attrs.update({
            'class': 'form-select',
            'size': '5',
        })

    def clean(self):
        """Проверяет выбор подписанта и доверенности(ей), если в пакет входят договор или соглашение."""
        cleaned_data = super().clean()
        selected_types = cleaned_data.get('consent_types')
        signer = cleaned_data.get('signer')
        poas = cleaned_data.get('powers_of_attorney')

        needs_signer = bool(selected_types and any(t.requires_signer for t in selected_types))
        if needs_signer and not signer:
            self.add_error(
                'signer',
                'Среди выбранных документов есть договор или соглашение — необходимо указать подписанта от работодателя.'
            )
        if signer and not signer.acts_by_charter and (not poas or len(poas) == 0):
            self.add_error(
                'powers_of_attorney',
                f'Подписант {signer.short_name} действует по доверенности — укажите доверенность(и) из реестра портала.'
            )
        return cleaned_data


class BiometricConsentFilterForm(forms.Form):
    """
    Форма фильтрации списка согласий
    """
    is_active = forms.ChoiceField(
        required=False,
        choices=[('', 'Все'), ('True', 'Действует'), ('False', 'Отозвано')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Поиск по номеру или ФИО...'})
    )