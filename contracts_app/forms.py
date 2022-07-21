from .models import Contract, Posts
from django import forms


class ContractsAddForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ('parent_category', 'contract_counteragent', 'internal_number', 'contract_number',
                  'date_conclusion', 'subject_contract', 'cost', 'type_of_contract',
                  'divisions', 'type_property', 'employee', 'closing_date', 'prolongation',
                  'comment', 'doc_file', 'access', 'executor')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-4'


class ContractsPostAddForm(forms.ModelForm):
    class Meta:
        model = Posts
        fields = ('contract_number', 'post_description', 'responsible_person')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
