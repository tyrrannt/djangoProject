from django import forms

from contracts_app.models import TypeDocuments
from customers_app.models import Division, Job, AccessLevel, DataBaseUser
from library_app.models import DocumentsJobDescription, DocumentsOrder


class DocumentsJobDescriptionAddForm(forms.ModelForm):
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = DocumentsJobDescription
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'document_division', 'employee', 'allowed_placed', 'validity_period_start', 'document_order',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name', 'document_job')


class DocumentsJobDescriptionUpdateForm(forms.ModelForm):
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = DocumentsJobDescription
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'document_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
                  'allowed_placed', 'actuality', 'document_name', 'document_order', 'document_job')


type_of_order = [
        ('1', 'Общая деятельность'),
        ('2', 'Личный состав')
    ]


class DocumentsOrderAddForm(forms.ModelForm):


    document_order_type = forms.ChoiceField(choices=type_of_order, label='Тип приказа')
    document_order_type.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all(), label='Ответственные лица')
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = DocumentsOrder
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'employee', 'allowed_placed', 'validity_period_start', 'document_order_type',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name')


class DocumentsOrderUpdateForm(forms.ModelForm):

    document_order_type = forms.ChoiceField(choices=type_of_order)
    document_order_type.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all(), label='Ответственные лица')
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = DocumentsOrder
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'employee', 'allowed_placed', 'validity_period_start', 'document_order_type',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name')
