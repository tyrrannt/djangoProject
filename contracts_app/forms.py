from django.forms import CheckboxSelectMultiple, SelectMultiple, ClearableFileInput

from customers_app.models import Division, DataBaseUser, Counteragent
from .models import Contract, Posts, TypeProperty, TypeDocuments, TypeContract
from django import forms


class ContractsAddForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all().order_by('last_name'))
    employee.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    type_of_contract = forms.ModelChoiceField(queryset=TypeContract.objects.all())
    type_of_contract.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    type_of_document = forms.ModelChoiceField(queryset=TypeDocuments.objects.all())
    type_of_document.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).order_by('code'))
    divisions.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    contract_counteragent = forms.ModelChoiceField(queryset=Counteragent.objects.all().order_by('short_name'))
    contract_counteragent.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    parent_category = forms.ModelChoiceField(queryset=Contract.objects.all(), required=False)
    parent_category.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    type_property = forms.ModelMultipleChoiceField(queryset=TypeProperty.objects.all(), required=False)
    type_property.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})

    class Meta:
        model = Contract
        fields = ['parent_category', 'contract_counteragent', 'contract_number',
                  'date_conclusion', 'subject_contract', 'cost', 'type_of_contract',
                  'divisions', 'type_property', 'employee', 'closing_date', 'prolongation',
                  'comment', 'doc_file', 'access', 'executor', 'type_of_document']
        widgets = {
            'doc_file': ClearableFileInput(attrs={'multiple': True})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contract_counteragent'].widget.attrs.update({
            'class': 'form-control mb-4 form-control-modern',
        })


class ContractsUpdateForm(forms.ModelForm):
    class Meta:
        model = Contract
        # fields = ('parent_category', 'contract_counteragent', 'internal_number', 'contract_number',
        #           'date_conclusion', 'subject_contract', 'cost', 'type_of_contract',
        #           'divisions', 'type_property', 'employee', 'closing_date', 'prolongation',
        #           'comment', 'date_entry', 'executor', 'doc_file', 'access', 'allowed_placed')
        fields = ('parent_category', 'contract_counteragent', 'type_of_contract', 'employee', 'contract_number',
                  'date_conclusion', 'closing_date', 'divisions', 'type_property', 'type_of_document', 'access',
                  'subject_contract', 'cost', 'prolongation', 'allowed_placed', 'doc_file')

    divisions = forms.ModelMultipleChoiceField(
        label='Подразделения',
        widget=SelectMultiple(),
        queryset=Division.objects.all())
    type_property = forms.ModelMultipleChoiceField(
        label='Тип имущества',
        widget=SelectMultiple(),
        queryset=TypeProperty.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        self.fields['divisions'].widget.attrs.update({
            'class': 'form-control mb-4 form-control-modern',
        })


class ContractsPostAddForm(forms.ModelForm):
    class Meta:
        model = Posts
        fields = ('contract_number', 'post_description', 'responsible_person')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class TypeDocumentsAddForm(forms.ModelForm):
    class Meta:
        model = TypeDocuments
        fields = ('type_document', 'short_name', 'file_name_prefix')


class TypeDocumentsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeDocuments
        fields = ('type_document', 'short_name', 'file_name_prefix')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class TypeContractsAddForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = ('type_contract',)


class TypeContractsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = ('type_contract',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''


class TypePropertysAddForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = ('type_property',)


class TypePropertysUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = ('type_property',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control form-control-modern'
            field.help_text = ''
