import datetime

from django import forms

from customers_app.models import Division, DataBaseUser
from hrdepartment_app.models import Medical, OfficialMemo, Purpose, ApprovalOficialMemoProcess


def present_or_future_date(value):
    if value < datetime.date.today():
        raise forms.ValidationError("Нельзя использовать прошедшую дату!")
    return value

class MedicalExaminationAddForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'person', 'organisation', 'working_status')


class MedicalExaminationUpdateForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'harmful')


class OfficialMemoAddForm(forms.ModelForm):
    memo_type = [
        ('1', 'Направление'),
        ('2', 'Продление')
    ]

    place_production_activity = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    official_memo_type = forms.ChoiceField(choices=memo_type)
    period_from = forms.DateField(label='Дата начала', validators=[present_or_future_date], required=True)
    period_for = forms.DateField(label='Дата окончания', validators=[present_or_future_date], required=True)
    class Meta:
        model = OfficialMemo
        fields = ('period_from', 'period_for', 'place_production_activity',
                  'person', 'purpose_trip', 'responsible')

    # def clean(self):
    #     # user age must be above 18 to register
    #     if self.cleaned_data.get('period_for') < self.cleaned_data.get('period_from'):
    #         msg = 'Дата начала не может быть больше даты окончания!'
    #         self.add_error(None, msg)


class OfficialMemoUpdateForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    memo_type = [
        ('1', 'Направление'),
        ('2', 'Продление')
    ]
    official_memo_type = forms.ChoiceField(choices=memo_type)
    place_production_activity = forms.ModelMultipleChoiceField(queryset=Division.objects.all())
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    order_date = forms.DateField(required=False)
    order_number = forms.CharField(required=False)

    class Meta:
        model = OfficialMemo
        fields = ('person', 'purpose_trip', 'period_from', 'period_for', 'place_production_activity',
                  'order_number', 'order_date', 'comments')

    def clean(self):
        # user age must be above 18 to register
        if self.cleaned_data.get('period_for') < self.cleaned_data.get('period_from'):
            msg = 'Дата начала не может быть больше даты окончания!'
            self.add_error(None, msg)



class ApprovalOficialMemoProcessAddForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_distributor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_department_staff.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.filter(docs__isnull=True))
    document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True, 'type': 'date'})
    accommodation = forms.ChoiceField(choices=type_of, required=False)
    accommodation.widget.attrs.update({'class': 'form-control form-control-modern'})
    order_number = forms.CharField(required=False)
    order_number.widget.attrs.update({'class': 'form-control form-control-modern'})
    order_date = forms.DateField(required=False)

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = '__all__'


class ApprovalOficialMemoProcessUpdateForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]

    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_distributor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_department_staff.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.all())
    document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    accommodation = forms.ChoiceField(choices=type_of, required=False)
    accommodation.widget.attrs.update({'class': 'form-control form-control-modern'})
    comments_for_approval = forms.CharField(required=False)
    comments_for_approval.widget.attrs.update({'class': 'form-control form-control-modern'})
    reason_for_approval = forms.CharField(required=False)
    reason_for_approval.widget.attrs.update({'class': 'form-control form-control-modern'})
    order_number = forms.CharField(required=False)
    order_number.widget.attrs.update({'class': 'form-control form-control-modern'})
    order_date = forms.DateField(required=False)

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = ('document', 'person_executor', 'submit_for_approval', 'comments_for_approval', 'person_agreement',
                  'document_not_agreed', 'reason_for_approval', 'person_distributor', 'location_selected',
                  'person_department_staff', 'process_accepted', 'accommodation', 'order_number', 'order_date')
