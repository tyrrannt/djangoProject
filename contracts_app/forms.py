from core import logger
from administration_app.utils import make_custom_field
from customers_app.models import Division, DataBaseUser
from .models import Contract, Posts, TypeProperty, TypeDocuments, TypeContract, Estate
from django import forms


class ContractsAddForm(forms.ModelForm):
    divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).order_by('code'))
    official_information = forms.CharField(required=False)

    class Meta:
        model = Contract
        fields = ['parent_category', 'contract_counteragent', 'contract_number', 'official_information',
                  'date_conclusion', 'subject_contract', 'cost', 'type_of_contract',
                  'divisions', 'type_property', 'employee', 'closing_date', 'prolongation',
                  'comment', 'doc_file', 'access', 'executor', 'type_of_document', 'allowed_placed']

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
                initial['parent_category'] = get_obj.pk
                initial['executor'] = get_obj.executor
                initial['allowed_placed'] = get_obj.allowed_placed
                kwargs['initial'] = initial

            except Contract.DoesNotExist:
                logger.error(f'Запись с UIN={self.parent} отсутствует в базе данных')
        else:
            initial = kwargs.get('initial', {})
            initial['parent_category'] = None
        super(ContractsAddForm, self).__init__(*args, **kwargs)
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.executor_user)
        self.fields["executor"].required = False

        for field in self.fields.values():
            make_custom_field(field)

    def clean(self):
        if self.cleaned_data['executor'] == None:
            self.cleaned_data['executor'] = DataBaseUser.objects.get(pk=self.executor_user)
        return self.cleaned_data


class ContractsUpdateForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.all().order_by('last_name').exclude(is_ppa=True), required=False)
    divisions = forms.ModelMultipleChoiceField(queryset=Division.objects.filter(active=True).order_by('code'))
    parent_category = forms.ModelChoiceField(
        queryset=Contract.objects.all().select_related('contract_counteragent', 'type_of_contract', 'type_of_document',
                                                       'executor'), required=False)

    class Meta:
        model = Contract
        fields = ('parent_category', 'contract_counteragent', 'type_of_contract', 'employee', 'contract_number',
                  'date_conclusion', 'closing_date', 'divisions', 'type_property', 'type_of_document', 'access',
                  'subject_contract', 'cost', 'prolongation', 'allowed_placed', 'doc_file', 'official_information',
                  'comment', 'actuality')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


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
        for field in self.fields.values():
            make_custom_field(field)


class TypeDocumentsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeDocuments
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class TypeContractsAddForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class TypeContractsUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeContract
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class TypePropertysAddForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class TypePropertysUpdateForm(forms.ModelForm):
    class Meta:
        model = TypeProperty
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class EstateAddForm(forms.ModelForm):
    class Meta:
        model = Estate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)


class EstateUpdateForm(forms.ModelForm):
    class Meta:
        model = Estate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            make_custom_field(field)
