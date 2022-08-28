from django import forms

from hrdepartment_app.models import Medical


class MedicalExaminationAddForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'person', 'organisation', 'working_status')


class MedicalExaminationUpdateForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'harmful')
