from django import forms

from customers_app.models import DataBaseUser
from library_app.models import HelpTopic, HelpCategory, HashTag, DocumentForm


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["text"].widget.attrs.update(
            {"class": "form-control django_ckeditor_5"}
        )
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
    sample = forms.URLField(required=False)

    class Meta:
        model = DocumentForm
        fields = ("title", "draft", "scan", "sample", "employee", "executor")

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(DocumentFormAddForm, self).__init__(*args, **kwargs)
        self.fields["executor"].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["executor"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )


class DocumentFormUpdateForm(forms.ModelForm):
    """
    Этот класс представляет форму для обновления объекта DocumentForm.

    Attributes:
        sample (forms.URLField): необязательное поле URL-адреса для предоставления образца документа.

    Meta:
       model (DocumentForm): соответствующая модель для этой формы.
       fields (list[str]): поля, которые будут отображаться в форме.

    """

    sample = forms.URLField(required=False)

    class Meta:
        model = DocumentForm
        fields = ("title", "draft", "scan", "sample", "employee")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super(DocumentFormUpdateForm, self).__init__(*args, **kwargs)
        self.fields["employee"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
