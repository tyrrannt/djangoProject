from django import forms

from customers_app.models import Division, DataBaseUser
from hrdepartment_app.models import Medical, OfficialMemo, Purpose, ApprovalOficialMemoProcess


class MedicalExaminationAddForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'person', 'organisation', 'working_status')


class MedicalExaminationUpdateForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'harmful')


class OfficialMemoAddForm(forms.ModelForm):

    place_production_activity = forms.ModelChoiceField(queryset=Division.objects.all())
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    class Meta:
        model = OfficialMemo
        fields = ('period_from', 'period_for',  'place_production_activity',
                  'person', 'purpose_trip')


class OfficialMemoUpdateForm(forms.ModelForm):
    class Meta:
        model = OfficialMemo
        fields = ('person', 'purpose_trip', 'period_from', 'period_for', 'place_production_activity', 'accommodation',
                  'order_number', 'order_date', 'comments')




class ApprovalOficialMemoProcessAddForm(forms.ModelForm):

    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.all())

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = '__all__'


class ApprovalOficialMemoProcessUpdateForm(forms.ModelForm):
    class Meta:
        model = ApprovalOficialMemoProcess
        fields = '__all__'