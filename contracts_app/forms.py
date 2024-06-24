from decouple import config
from django.forms import CheckboxSelectMultiple, SelectMultiple, ClearableFileInput
from loguru import logger

from administration_app.utils import make_custom_field
from customers_app.models import Division, DataBaseUser, Counteragent
from .models import Contract, Posts, TypeProperty, TypeDocuments, TypeContract, Estate
from django import forms


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))

class ContractsAddForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all().order_by('last_name'), required=False)
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
    parent_category = forms.ModelChoiceField(queryset=Contract.objects.filter(parent_category__isnull=True).select_related('contract_counteragent', 'type_of_contract', 'type_of_document', 'executor'),
                                             required=False)
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
                  'comment', 'doc_file', 'access', 'executor', 'type_of_document', 'allowed_placed']
        # widgets = {
        #     'doc_file': ClearableFileInput(attrs={'multiple': True})
        # }

    def __init__(self, *args, **kwargs):
        self.parent = kwargs.pop('parent')
        self.executor_user = kwargs.pop('executor')
        if self.parent:
            initial = kwargs.get('initial', {})
            try:
                get_obj = Contract.objects.get(pk=self.parent)
                initial['contract_number'] = get_obj.contract_number
                initial['date_conclusion'] = get_obj.date_conclusion
                initial['closing_date'] = get_obj.closing_date
                initial['contract_counteragent'] = get_obj.contract_counteragent
                initial['type_of_contract'] = get_obj.type_of_contract
                initial['prolongation'] = get_obj.prolongation
                initial['type_property'] = get_obj.type_property.all()
                initial['divisions'] = get_obj.divisions.all()
                initial['employee'] = get_obj.employee.all()
                initial['cost'] = get_obj.cost
                initial['access'] = get_obj.access
                initial['subject_contract'] = get_obj.subject_contract
                initial['subject_contract'] = get_obj.subject_contract
                initial['parent_category'] = get_obj
                initial['executor'] = get_obj.executor
                initial['allowed_placed'] = get_obj.allowed_placed
                kwargs['initial'] = initial
            except Contract.DoesNotExist:
                logger.error(f'Запись с UIN={self.parent} отсутствует в базе данных')
        super(ContractsAddForm, self).__init__(*args, **kwargs)
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.executor_user)
        for field in self.fields:
            make_custom_field(self.fields[field])
        # self.fields['executor'].widget.attrs.update(
        #     {'class': 'form-control form-control-modern'})
        # self.fields['contract_counteragent'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern',
        # })
        # self.fields['contract_number'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern',
        # })
        # self.fields['date_conclusion'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern',
        # })
        # self.fields['closing_date'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern',
        # })
        # self.fields['cost'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern',
        # })
        # self.fields['subject_contract'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern', 'rows': '6'
        # })
        # self.fields['comment'].widget.attrs.update({
        #     'class': 'form-control mb-4 form-control-modern', 'rows': '6'
        # })


class ContractsUpdateForm(forms.ModelForm):

    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all().order_by('last_name'), required=False)
    divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).order_by('code'))
    parent_category = forms.ModelChoiceField(queryset=Contract.objects.all().select_related('contract_counteragent', 'type_of_contract', 'type_of_document', 'executor'), required=False)

    class Meta:
        model = Contract
        fields = ('parent_category', 'contract_counteragent', 'type_of_contract', 'employee', 'contract_number',
                  'date_conclusion', 'closing_date', 'divisions', 'type_property', 'type_of_document', 'access',
                  'subject_contract', 'cost', 'prolongation', 'allowed_placed', 'doc_file', 'official_information',)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


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
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TypeDocumentsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeDocuments
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TypeContractsAddForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TypeContractsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TypePropertysAddForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TypePropertysUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class EstateAddForm(forms.ModelForm):
    class Meta:
        model = Estate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class EstateUpdateForm(forms.ModelForm):
    class Meta:
        model = Estate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])
