from django import forms

from contracts_app.models import TypeDocuments
from customers_app.models import Division, Job, AccessLevel, DataBaseUser
from library_app.models import HelpTopic, HelpCategory, HashTag


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
