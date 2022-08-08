from django.forms import CheckboxSelectMultiple, SelectMultiple

from customers_app.models import Division
from .models import Contract, Posts
from django import forms


class ContractsAddForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['parent_category', 'contract_counteragent', 'internal_number', 'contract_number',
                  'date_conclusion', 'subject_contract', 'cost', 'type_of_contract',
                  'divisions', 'type_property', 'employee', 'closing_date', 'prolongation',
                  'comment', 'doc_file', 'access', 'executor', 'type_of_document']

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
                  'date_conclusion', 'closing_date', 'divisions', 'type_property', 'type_of_document',
                  'subject_contract', 'cost', 'internal_number', 'prolongation', 'allowed_placed')

    divisions = forms.ModelMultipleChoiceField(
        label='Подразделения',
        widget=SelectMultiple(),
        queryset=Division.objects.all())

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
