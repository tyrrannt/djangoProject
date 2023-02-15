from django import forms

from contracts_app.models import TypeDocuments
from customers_app.models import Division, Job
from library_app.models import DocumentsJobDescription, DocumentsOrder


class DocumentsJobDescriptionAddForm(forms.ModelForm):
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = DocumentsJobDescription
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'allowed_placed', 'validity_period_start', 'document_order',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name', 'document_job')

#
# class DocumentsJobDescriptionDetailForm(forms.ModelForm):
#     type_of_document = forms.ModelChoiceField(queryset=TypeDocuments.objects.all())
#     type_of_document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
#     document_division = forms.ModelChoiceField(queryset=Division.objects.all())
#     document_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
#     class Meta:
#         model = DocumentsJobDescription
#         fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
#                   'document_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
#                   'allowed_placed', 'actuality', 'document_name')


class DocumentsJobDescriptionUpdateForm(forms.ModelForm):
    type_of_document = forms.ModelChoiceField(queryset=TypeDocuments.objects.all())
    type_of_document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = DocumentsJobDescription
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
                  'allowed_placed', 'actuality', 'document_name', 'document_order', 'document_job')
