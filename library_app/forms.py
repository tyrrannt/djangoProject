from copy import deepcopy
from dataclasses import fields

from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget

from administration_app.utils import make_custom_field
from customers_app.models import DataBaseUser, Division
from library_app.models import HelpTopic, HelpCategory, HashTag, DocumentForm, Poem, CompanyEvent


class HelpItemAddForm(forms.ModelForm):
    hash_tag = forms.ModelMultipleChoiceField(
        queryset=HashTag.objects.all(), label="Хэштег"
    )
    hash_tag.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    category = forms.ModelChoiceField(
        queryset=HelpCategory.objects.all(), label="Категория"
    )
    category.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = HelpTopic
        fields = "__all__"
        widgets = {
            "text": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"}, config_name="comment"
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].required = False


class HelpItemUpdateForm(forms.ModelForm):
    hash_tag = forms.ModelMultipleChoiceField(
        queryset=HashTag.objects.all(), label="Хэштег"
    )
    hash_tag.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    category = forms.ModelChoiceField(
        queryset=HelpCategory.objects.all(), label="Категория"
    )
    category.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = HelpTopic
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].widget.attrs.update(
            {"class": "form-control django_ckeditor_5"}
        )
        self.fields["text"].required = False


class DocumentFormAddForm(forms.ModelForm):
    division = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).exclude(name__icontains='Основное подразделение'))

    class Meta:
        model = DocumentForm
        fields = ("title", "draft", "draft_visible", "scan", "sample", "division", "employee", "executor")

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(DocumentFormAddForm, self).__init__(*args, **kwargs)
        self.fields["executor"].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].queryset = DataBaseUser.objects.filter(is_active=True).exclude(username="proxmox")
        self.fields["division"].widget.attrs.update(
            {
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["employee"].widget.attrs.update(
            {
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["draft"].widget.attrs.update(
            {"accept": ".doc, .docx, .xls, .xlsx"}
        )
        self.fields["scan"].widget.attrs.update(
            {"accept": ".pdf"}
        )
        self.fields["sample"].widget.attrs.update(
            {"accept": ".jpg, .jpeg, .png, .pdf"}
        )
        for field in self.fields:
            if field not in ["division", "employee"]:
                make_custom_field(self.fields[field])


class DocumentFormUpdateForm(forms.ModelForm):
    """
    Этот класс представляет форму для обновления объекта DocumentForm.

    Attributes:
        sample (forms.URLField): необязательное поле URL-адреса для предоставления образца документа.

    Meta:
       model (DocumentForm): соответствующая модель для этой формы.
       fields (list[str]): поля, которые будут отображаться в форме.

    """

    class Meta:
        model = DocumentForm
        fields = ("title", "draft", "draft_visible", "scan", "sample", "division", "employee")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(DocumentFormUpdateForm, self).__init__(*args, **kwargs)
        self.fields["division"].queryset = Division.objects.filter(active=True).exclude(name__icontains='Основное подразделение')
        self.fields["draft"].widget.attrs.update(
            {"accept": ".doc, .docx, .xls, .xlsx"}
        )
        self.fields["scan"].widget.attrs.update(
            {"accept": ".pdf"}
        )
        self.fields["sample"].widget.attrs.update(
            {"accept": ".jpg, .jpeg, .png, .pdf"}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])

class PoemForm(forms.ModelForm):
    class Meta:
        model = Poem
        fields = ['title', 'content']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

class VoteConfirmationForm(forms.Form):
    confirm_vote = forms.BooleanField(label='Подтвердите переголосование')


class CompanyEventForm(forms.ModelForm):
    class Meta:
        model = CompanyEvent
        fields = ['title', 'event_date', 'decoding', 'results', 'event_report', 'event_media', 'participants']
        widgets = {
            "decoding": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"}, config_name="extends"
            ),
            "results": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"}, config_name="extends"
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["results"].required = False
        self.fields["event_report"].required = False
        self.fields["event_media"].required = False
        self.fields["participants"].required = False
        custom_fields = self.fields.copy()
        custom_fields.pop("results")
        custom_fields.pop("decoding")

        for field in custom_fields:
            make_custom_field(self.fields[field])