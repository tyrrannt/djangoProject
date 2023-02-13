from django import forms

from contracts_app.models import TypeDocuments
from library_app.models import DocumentsJobDescription


class DocumentsJobDescriptionAddForm(forms.ModelForm):
    class Meta:
        model = DocumentsJobDescription
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'allowed_placed', 'validity_period_start',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name')


class DocumentsJobDescriptionDetailForm(forms.ModelForm):
    type_of_document = forms.ModelChoiceField(queryset=TypeDocuments.objects.all())
    type_of_document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = DocumentsJobDescription
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
                  'allowed_placed', 'actuality', 'document_name')


class DocumentsJobDescriptionUpdateForm(forms.ModelForm):
    type_of_document = forms.ModelChoiceField(queryset=TypeDocuments.objects.all())
    type_of_document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = DocumentsJobDescription
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
                  'allowed_placed', 'actuality', 'document_name')
