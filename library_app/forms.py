from django import forms

from library_app.models import Documents


class DocumentsAddForm(forms.ModelForm):
    class Meta:
        model = Documents
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'allowed_placed', 'validity_period_start',
                  'validity_period_end', 'actuality', 'previous_document')


class DocumentsUpdateForm(forms.ModelForm):
    class Meta:
        model = Documents
        fields = ('type_of_document', 'executor', 'document_date', 'document_number', 'doc_file', 'access',
                  'document_division', 'employee', 'allowed_placed', 'validity_period_start',
                  'validity_period_end', 'actuality', 'previous_document')

