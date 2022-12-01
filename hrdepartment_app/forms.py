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
    person.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})

    class Meta:
        model = OfficialMemo
        fields = ('period_from', 'period_for', 'place_production_activity',
                  'person', 'purpose_trip')


class OfficialMemoUpdateForm(forms.ModelForm):
    place_production_activity = forms.ModelChoiceField(queryset=Division.objects.all())
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    order_date = forms.DateField(required=False)
    order_number = forms.CharField(required=False)
    accommodation = forms.MultipleChoiceField(choices=OfficialMemo.type_of)
    accommodation.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    class Meta:
        model = OfficialMemo
        fields = ('person', 'purpose_trip', 'period_from', 'period_for', 'place_production_activity', 'accommodation',
                  'order_number', 'order_date', 'comments')



class ApprovalOficialMemoProcessAddForm(forms.ModelForm):
    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_distributor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_department_staff.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.filter(docs__isnull=True), required=False)
    document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = '__all__'


class ApprovalOficialMemoProcessUpdateForm(forms.ModelForm):
    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern'})
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern'})
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_distributor.widget.attrs.update({'class': 'form-control form-control-modern'})
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_department_staff.widget.attrs.update({'class': 'form-control form-control-modern'})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.all())
    document.widget.attrs.update({'class': 'form-control form-control-modern'})

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = '__all__'
