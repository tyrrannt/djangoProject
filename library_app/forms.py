from django import forms

from contracts_app.models import TypeDocuments
from customers_app.models import Division, Job, AccessLevel, DataBaseUser
from library_app.models import HelpTopic, HelpCategory, HashTag, DocumentForm


class HelpItemAddForm(forms.ModelForm):
    hash_tag = forms.ModelMultipleChoiceField(queryset=HashTag.objects.all(), label='Хэштег')
    hash_tag.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    category = forms.ModelChoiceField(queryset=HelpCategory.objects.all(), label='Категория')
    category.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = HelpTopic
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields["description"].required = False
        self.fields['text'].widget.attrs.update({'class': 'form-control django_ckeditor_5'})
        self.fields['text'].required = False


class HelpItemUpdateForm(forms.ModelForm):
    hash_tag = forms.ModelMultipleChoiceField(queryset=HashTag.objects.all(), label='Хэштег')
    hash_tag.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    category = forms.ModelChoiceField(queryset=HelpCategory.objects.all(), label='Категория')
    category.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = HelpTopic
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.fields["description"].required = False
        self.fields['text'].widget.attrs.update({'class': 'form-control django_ckeditor_5'})
        self.fields['text'].required = False


class DocumentFormAddForm(forms.ModelForm):
    # employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all().only('pk'), label='Ответственные лица')
    # employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    # executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all().only('pk'), label='Исполнитель')
    # executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    sample = forms.URLField(required=False)
    class Meta:
        model = DocumentForm
        fields = ('title', 'draft', 'scan', 'sample', 'employee', 'executor')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop('user')
        super(DocumentFormAddForm, self).__init__(*args, **kwargs)
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields['employee'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
        self.fields['executor'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})




class DocumentFormUpdateForm(forms.ModelForm):
    sample = forms.URLField(required=False)
    class Meta:
        model = DocumentForm
        fields = ('title', 'draft', 'scan', 'sample', 'employee')
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(DocumentFormUpdateForm, self).__init__(*args, **kwargs)
        self.fields['employee'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

