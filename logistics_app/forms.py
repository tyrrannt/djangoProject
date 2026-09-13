import re
from typing import Any, Dict, Optional

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from administration_app.utils import make_custom_field
from customers_app.models import Counteragent, DataBaseUser, Division
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowComment,
    DocFlowDocument,
    DocFlowDocumentType,
    DocFlowFile,
    DocFlowFileVersion,
    DocFlowRouteStep,
    DocFlowRouteStepTemplate,
    DocFlowRouteTemplate,
    Package,
    WayBill,
)


class WayBillCreateForm(forms.ModelForm):
    class Meta:
        model = WayBill
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillCreateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])
        # self.fields["content"].widget.attrs.update(
        #     {"class": "ui-widget"}
        # )


class WayBillForm(forms.ModelForm):
    class Meta:
        model = WayBill
        fields = ['document_date', 'place_of_departure', 'comment', 'place_division', 'sender', 'state', 'responsible',
                  'executor', 'urgency']

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class WayBillUpdateForm(forms.ModelForm):
    place_division = forms.ModelChoiceField(
        queryset=Division.objects.filter(active=True).exclude(name__icontains='Основное подразделение'),
        label="Подразделение")

    class Meta:
        model = WayBill
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """

        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(WayBillUpdateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class PackageCreateForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """

        # self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        super(PackageCreateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


# PackageInlineFormSet = inlineformset_factory(Package, WayBill, form=PackageCreateForm, extra=1)
WayBillInlineFormSet = inlineformset_factory(Package, WayBill, form=WayBillForm, fk_name='package_number',
                                             extra=1, can_delete=True, can_delete_extra=True,
                                             formset=BaseInlineFormSet, )


# ==============================================================================
# ФОРМЫ ПОДСИСТЕМЫ ЭЛЕКТРОННОГО ДОКУМЕНТООБОРОТА (СЭД)
# ==============================================================================

class DocFlowDocumentForm(forms.ModelForm):
    """Форма создания и редактирования учетной карточки документа СЭД."""

    route_template = forms.ModelChoiceField(
        queryset=DocFlowRouteTemplate.objects.all(),
        label="Шаблон маршрута согласования",
        required=False,
        help_text="Выберите типовой маршрут или оставьте пустым для применения маршрута по умолчанию.",
    )
    initial_file = forms.FileField(
        label="Основной файл документа",
        required=False,
        help_text="Прикрепите исходный проект документа (PDF, Word, Excel, скан).",
    )
    initial_file_title = forms.CharField(
        label="Название файла",
        max_length=255,
        required=False,
        initial="Основной документ",
    )

    class Meta:
        model = DocFlowDocument
        fields = [
            "doc_type",
            "title",
            "flow_type",
            "urgency",
            "responsible",
            "counteragent",
            "counteragent_contact_email",
            "deadline",
            "description",
            "related_waybill",
            "related_package",
            "related_contract",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Введите тему или краткое наименование документа"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Подробное описание, примечания или сопроводительный текст"}),
            "counteragent_contact_email": forms.EmailInput(attrs={"placeholder": "email@counteragent.ru"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с настройкой виджетов."""
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            make_custom_field(field)


class DocFlowApprovalActionForm(forms.Form):
    """Форма наложения визы согласования с Простой Электронной Подписью (ПЭП)."""

    comment = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": "form-control",
            "placeholder": "Комментарий / особое мнение (необязательно)",
        }),
        required=False,
        label="Комментарий / Резолюция",
    )
    is_minor_edit = forms.BooleanField(
        required=False,
        label="Согласовано с редакционными замечаниями",
        help_text="Отметьте, если замечания носят характер мелких правок и не требуют отката процесса.",
    )
    confirm_pep = forms.BooleanField(
        required=True,
        initial=True,
        label="Подтверждаю наложение Простой Электронной Подписи (ПЭП) в СЭД АК «БАРКОЛ»",
    )


class DocFlowRollbackActionForm(forms.Form):
    """Форма выполнения многошагового отката на выбранный предшествующий этап."""

    target_step_order = forms.ChoiceField(
        label="Выберите этап для отката",
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control",
            "placeholder": "Опишите подробные замечания и причину возврата на данный этап...",
        }),
        required=True,
        label="Причина отката и замечания",
    )

    def __init__(self, *args, document=None, current_step=None, **kwargs):
        """Динамически заполняет список доступных пройденных этапов для отката."""
        super().__init__(*args, **kwargs)
        if document and current_step:
            choices = []
            previous_steps = document.route_steps.filter(
                step_order__lt=current_step.step_order,
                can_rollback_to=True,
            ).order_by("step_order")

            for s in previous_steps:
                assignee = s.assigned_user.get_full_name() if s.assigned_user else (s.assigned_division.name if s.assigned_division else "Группа")
                choices.append((str(s.step_order), f"Шаг {s.step_order}: {s.step_name} ({assignee})"))

            self.fields["target_step_order"].choices = choices


class DocFlowReworkActionForm(forms.Form):
    """Форма возврата документа автору на доработку."""

    comment = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 4,
            "class": "form-control",
            "placeholder": "Опишите перечень замечаний, которые автор обязан исправить...",
        }),
        required=True,
        label="Перечень замечаний для доработки",
    )


class DocFlowFileUploadForm(forms.Form):
    """Форма загрузки новой версии файла документа СЭД."""

    file = forms.FileField(
        label="Выберите обновленный файл",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 3,
            "class": "form-control",
            "placeholder": "Что было изменено в данной версии (например, обновлена спецификация цен)...",
        }),
        required=False,
        label="Комментарий к изменениям",
    )
    is_reviewer_edit = forms.BooleanField(
        required=False,
        label="Правка согласующего лица (минорная версия vX.1)",
        help_text="Отметьте, если вы загружаете файл со своими редакторскими пометками.",
    )


class DocFlowCommentForm(forms.ModelForm):
    """Форма добавления сообщения во внутренний чат документа."""

    class Meta:
        model = DocFlowComment
        fields = ["text", "parent"]
        widgets = {
            "text": forms.Textarea(attrs={
                "rows": 3,
                "class": "form-control",
                "placeholder": "Напишите сообщение, вопрос или уточнение коллегам...",
            }),
            "parent": forms.HiddenInput(),
        }


def transliterate_to_code(text: str) -> str:
    """Транслитерирует русский текст в верхнерегистровый латинский символьный код.

    Args:
        text (str): Исходное наименование вида документа на русском языке.

    Returns:
        str: Символьный код латиницей в верхнем регистре с подчеркиваниями (например, 'DOGOVOR_POSTAVKI_MTR').
    """
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    cleaned_text = text.strip().lower()
    char_list = []
    for ch in cleaned_text:
        if ch in translit_map:
            char_list.append(translit_map[ch])
        elif ch.isalnum():
            char_list.append(ch)
        else:
            char_list.append('_')
    raw_code = "".join(char_list)
    code = re.sub(r'_+', '_', raw_code).strip('_').upper()
    return code or "DOC_TYPE"


class DocFlowDocumentTypeForm(forms.ModelForm):
    """Форма создания и редактирования вида документа СЭД с автогенерацией символьного кода."""

    code = forms.CharField(
        required=False,
        label="Символьный код (латиницей)",
        widget=forms.TextInput(attrs={
            "placeholder": "Генерируется автоматически из наименования...",
            "class": "form-control text-uppercase font-monospace",
            "id": "id_code",
        }),
        help_text="Оставьте пустым для автоматической генерации из названия или задайте свой уникальный код.",
    )

    class Meta:
        model = DocFlowDocumentType
        fields = [
            "name",
            "category",
            "code",
            "description",
            "default_sla_hours",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Например: Договор поставки МТР / Служебная записка",
                "id": "id_name",
            }),
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Описание регламента и назначения вида документа"}),
            "default_sla_hours": forms.NumberInput(attrs={"min": 1, "placeholder": "24"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы вида документа."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)

    def clean_code(self) -> str:
        """Валидирует и при необходимости автоматически генерирует уникальный символьный код."""
        code = self.cleaned_data.get("code", "").strip()
        name = self.cleaned_data.get("name", "").strip()

        if not code and name:
            base_code = transliterate_to_code(name)
            code = base_code
            counter = 1
            qs = DocFlowDocumentType.objects.filter(code=code)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.exists():
                code = f"{base_code}_{counter}"
                counter += 1
                qs = DocFlowDocumentType.objects.filter(code=code)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
        elif code:
            # Форматируем введенный вручную код
            code = re.sub(r'[^A-Za-z0-9_]', '_', code).strip('_').upper()
            code = re.sub(r'_+', '_', code)

        if not code:
            code = "DOC_TYPE"

        return code


class DocFlowRouteTemplateForm(forms.ModelForm):
    """Форма создания и редактирования шаблона маршрута согласования."""

    class Meta:
        model = DocFlowRouteTemplate
        fields = ["name", "doc_type", "is_default", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Например, «Маршрут согласования ученического договора»"}),
            "doc_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Краткое описание регламента маршрута"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с настройкой виджетов."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class DocFlowRouteStepTemplateForm(forms.ModelForm):
    """Форма редактирования шага шаблона маршрута."""

    assigned_user = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        label="Назначенный сотрудник",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    assigned_users = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by("last_name", "first_name"),
        required=False,
        label="Группа сотрудников (для параллельного)",
        widget=forms.SelectMultiple(attrs={"class": "form-select"})
    )
    assigned_division = forms.ModelChoiceField(
        queryset=Division.objects.all().order_by("name"),
        required=False,
        label="Назначенное подразделение",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = DocFlowRouteStepTemplate
        fields = [
            "step_order",
            "step_name",
            "step_type",
            "assigned_user",
            "assigned_users",
            "assigned_division",
            "sla_hours",
            "allow_reviewer_file_edit",
            "can_rollback_to",
        ]
        widgets = {
            "step_order": forms.NumberInput(attrs={"class": "form-control step-order-field", "min": 1}),
            "step_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например: Согласование руководителем"}),
            "step_type": forms.Select(attrs={"class": "form-select step-type-select"}),
            "sla_hours": forms.NumberInput(attrs={"class": "form-control", "min": 1, "placeholder": "24"}),
            "allow_reviewer_file_edit": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "can_rollback_to": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы этапа."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


DocFlowRouteStepTemplateFormSet = inlineformset_factory(
    parent_model=DocFlowRouteTemplate,
    model=DocFlowRouteStepTemplate,
    form=DocFlowRouteStepTemplateForm,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)

