import datetime

from decouple import config
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from loguru import logger

from customers_app.models import Division, DataBaseUser, Job, HarmfulWorkingConditions, AccessLevel
from hrdepartment_app.models import Medical, OfficialMemo, Purpose, ApprovalOficialMemoProcess, \
    BusinessProcessDirection, MedicalOrganisation, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity, \
    ReasonForCancellation, OrderDescription, ReportCard, Provisions

logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'))


def present_or_future_date(value):
    if value < datetime.date.today() - datetime.timedelta(days=60):
        raise forms.ValidationError("Нельзя использовать прошедшую дату!")
    return value


class MedicalOrganisationAddForm(forms.ModelForm):
    class Meta:
        model = MedicalOrganisation
        fields = ('ref_key', 'description', 'ogrn', 'address', 'email', 'phone')


class MedicalOrganisationUpdateForm(forms.ModelForm):
    class Meta:
        model = MedicalOrganisation
        fields = ('ref_key', 'description', 'ogrn', 'address', 'email', 'phone')


class MedicalExaminationAddForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ('number', 'person', 'organisation', 'working_status')


class MedicalExaminationUpdateForm(forms.ModelForm):
    harmful = forms.ModelMultipleChoiceField(HarmfulWorkingConditions.objects.all())
    harmful.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})

    class Meta:
        model = Medical
        fields = ('number', 'harmful')


class OfficialMemoAddForm(forms.ModelForm):
    memo_type = [
        ('1', 'Направление'),
        ('2', 'Продление'),
        ('3', 'Без выезда'),
    ]
    type_of_trip = [
        ('1', 'Служебная поездка'),
        ('2', 'Командировка')
    ]
    place_production_activity = forms.ModelMultipleChoiceField(queryset=PlaceProductionActivity.objects.all())
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    place_departure = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.all())
    place_departure.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all().order_by('last_name'))
    person.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    official_memo_type = forms.ChoiceField(choices=memo_type)
    type_trip = forms.ChoiceField(choices=type_of_trip)
    period_from = forms.DateField(label='Дата начала', validators=[present_or_future_date], required=True)
    period_for = forms.DateField(label='Дата окончания', validators=[present_or_future_date], required=True)
    document_extension = forms.ModelChoiceField(queryset=OfficialMemo.objects.all(), required=False)
    document_extension.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = OfficialMemo
        fields = ('period_from', 'period_for', 'place_production_activity', 'place_departure',
                  'person', 'purpose_trip', 'responsible', 'type_trip', 'official_memo_type', 'document_extension')

    def clean(self):
        cleaned_data = super().clean()
        official_memo_type = cleaned_data.get("official_memo_type")
        document_extension = cleaned_data.get("document_extension")
        if official_memo_type == '2' and not document_extension:
            # Сохраняем только если оба поля действительны.
            raise ValidationError(
                "Ошибка создания документа. Для продления необходимо указать документ основания!!!"
            )


class OfficialMemoUpdateForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    memo_type = [
        ('1', 'Направление'),
        ('2', 'Продление'),
        ('3', 'Без выезда'),
    ]
    type_of_trip = [
        ('1', 'Служебная поездка'),
        ('2', 'Командировка')
    ]
    place_departure = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.all())
    place_departure.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    official_memo_type = forms.ChoiceField(choices=memo_type)
    place_production_activity = forms.ModelMultipleChoiceField(queryset=PlaceProductionActivity.objects.all())
    place_production_activity.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {'class': 'form-control form-control-modern data-plugin-selectTwo', 'data-plugin-selectTwo': True})
    type_trip = forms.ChoiceField(choices=type_of_trip)
    document_extension = forms.ModelChoiceField(queryset=OfficialMemo.objects.all(), required=False)
    document_extension.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = OfficialMemo
        fields = ('person', 'purpose_trip', 'period_from', 'period_for', 'place_production_activity',
                  'comments', 'type_trip', 'official_memo_type', 'place_departure', 'document_extension')

    def clean(self):
        # user age must be above 18 to register
        try:
            if self.cleaned_data.get('period_for') < self.cleaned_data.get('period_from'):
                msg = 'Дата начала не может быть больше даты окончания!'
                self.add_error(None, msg)
        except Exception as _ex:
            logger.error(
                f"Ошибка проверки времени: {self.cleaned_data.get('period_for')} {self.cleaned_data.get('period_from')} {_ex}")


class ApprovalOficialMemoProcessAddForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]
    person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.filter(docs__isnull=True))
    document.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True, 'type': 'date'})

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = ('document', 'person_executor', 'submit_for_approval', 'comments_for_approval', 'person_agreement',
                  'start_date_trip', 'end_date_trip')


class ApprovalOficialMemoProcessUpdateForm(forms.ModelForm):
    type_of = [
        ('1', 'Квартира'),
        ('2', 'Гостиница')
    ]

    person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_clerk = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_clerk.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_hr = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_hr.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_distributor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_distributor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_department_staff = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_department_staff.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_accounting = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    person_accounting.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.all())
    document.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    accommodation = forms.ChoiceField(choices=ApprovalOficialMemoProcess.type_of, required=False)
    accommodation.widget.attrs.update({'class': 'form-control form-control-modern'})
    comments_for_approval = forms.CharField(required=False)
    comments_for_approval.widget.attrs.update({'class': 'form-control form-control-modern'})
    reason_for_approval = forms.CharField(required=False)
    prepaid_expense = forms.CharField(required=False)
    reason_for_approval.widget.attrs.update({'class': 'form-control form-control-modern'})
    order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all(), required=False)
    order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    number_business_trip_days = forms.IntegerField(required=False)
    number_flight_days = forms.IntegerField(required=False)
    prepaid_expense_summ = forms.DecimalField(required=False)

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = ('document', 'person_executor', 'submit_for_approval', 'comments_for_approval', 'person_agreement',
                  'document_not_agreed', 'reason_for_approval', 'person_distributor', 'location_selected',
                  'person_department_staff', 'process_accepted', 'accommodation', 'order', 'person_accounting',
                  'prepaid_expense', 'accepted_accounting', 'person_clerk', 'originals_received', 'person_hr',
                  'hr_accepted', 'number_business_trip_days', 'number_flight_days', 'start_date_trip',
                  'end_date_trip', 'date_transfer_hr', 'date_transfer_accounting', 'date_receipt_original',
                  'originals_docs_comment', 'prepaid_expense_summ', 'submitted_for_signature')

    def clean(self):
        cleaned_data = super().clean()
        person_agreement = cleaned_data.get("person_agreement")
        document_not_agreed = cleaned_data.get("document_not_agreed")
        person_distributor = cleaned_data.get("person_distributor")
        location_selected = cleaned_data.get("location_selected")
        accommodation = cleaned_data.get("accommodation")
        person_department_staff = cleaned_data.get("person_department_staff")
        process_accepted = cleaned_data.get("process_accepted")
        order = cleaned_data.get("order")
        d1 = str(cleaned_data.get("document"))
        originals_received = cleaned_data.get("originals_received")

        if not person_agreement and document_not_agreed:
            # Сохраняем только если оба поля действительны.
            raise ValidationError(
                "Ошибка согласования документа. Поле руководителя не заполнено!!!"
            )
        if (not person_distributor or not accommodation) and location_selected:
            # Сохраняем только если оба поля действительны.
            print(person_distributor, accommodation, location_selected)
            raise ValidationError(
                "Ошибка согласования места проживания. Лицо ответственное за НО не заполнено!!!"
            )
        if (not person_department_staff or not order) and process_accepted:
            # Сохраняем только если оба поля действительны.
            raise ValidationError(
                "Ошибка приема документа в ОК. Ответственное лицо не заполнено!!!"
            )
        if process_accepted:
            if not location_selected:
                raise ValidationError(
                    "Ошибка приема документа в ОК. Место проживания не установлено!!!"
                )
        if originals_received:
            if not process_accepted:
                if d1[:4] != '(БВ)':
                    raise ValidationError(
                        "Ошибка приема документа делопроизводителем. Приказ не создан!!!"
                    )
        if location_selected:
            if not document_not_agreed:
                raise ValidationError(
                    "Ошибка в назначении места проживания. Документ не согласован руководителем!!!"
                )


class ApprovalOficialMemoProcessChangeForm(forms.ModelForm):
    reason_cancellation = forms.ModelChoiceField(queryset=ReasonForCancellation.objects.all(), required=False)
    reason_cancellation.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = ('cancellation', 'reason_cancellation')

    def clean(self):
        cleaned_data = super().clean()
        cancellation = cleaned_data.get("cancellation")
        reason_cancellation = cleaned_data.get("reason_cancellation")
        if not cancellation:
            raise ValidationError(
                "Ошибка! Не установлен переключатель отмены документа"
            )
        if not reason_cancellation:
            raise ValidationError(
                "Ошибка! Не выбрана причина отмены"
            )


class BusinessProcessDirectionAddForm(forms.ModelForm):
    type_of = [
        ('1', 'SP')
    ]
    business_process_type = forms.ChoiceField(choices=type_of)
    person_agreement = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_executor = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    clerk = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    clerk.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_hr = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_hr.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    date_start = forms.DateField(required=False)
    date_end = forms.DateField(required=False)

    class Meta:
        model = BusinessProcessDirection
        fields = '__all__'


class BusinessProcessDirectionUpdateForm(forms.ModelForm):
    type_of = [
        ('1', 'SP')
    ]
    business_process_type = forms.ChoiceField(choices=type_of)
    person_agreement = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_executor = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    clerk = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    clerk.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    person_hr = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_hr.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    date_start = forms.DateField(required=False)
    date_end = forms.DateField(required=False)

    class Meta:
        model = BusinessProcessDirection
        fields = '__all__'


class PurposeAddForm(forms.ModelForm):
    class Meta:
        model = Purpose
        fields = '__all__'


class PurposeUpdateForm(forms.ModelForm):
    class Meta:
        model = Purpose
        fields = '__all__'


class DocumentsJobDescriptionAddForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
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
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
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
    document_foundation = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.filter(Q(order=None) & Q(docs__isnull=False)).exclude(cancellation=True).exclude(
            official_memo_type='3'), required=False)
    document_foundation.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_name.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order_type = forms.ChoiceField(choices=type_of_order, label='Тип приказа')
    document_order_type.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all(), label='Ответственные лица')
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    validity_period_start = forms.DateField(required=False)
    validity_period_end = forms.DateField(required=False)

    class Meta:
        model = DocumentsOrder
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'employee', 'allowed_placed', 'validity_period_start', 'document_order_type',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name', 'document_foundation')

    def clean(self):
        print(datetime.date.today)
        cleaned_data = super().clean()
        scan_file = cleaned_data.get("scan_file")
        ext = str(scan_file).split('.')[-1]
        if scan_file and ext != 'pdf':
            # Сохраняем только если оба поля действительны.
            raise ValidationError("Скан документа должен быть в формате PDF")

        document_number = cleaned_data.get("document_number")
        exist_doc = DocumentsOrder.objects.filter()


class DocumentsOrderUpdateForm(forms.ModelForm):
    document_foundation = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False)
    document_foundation.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_name.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order_type = forms.ChoiceField(choices=type_of_order)
    document_order_type.widget.attrs.update(
        {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all(), label='Ответственные лица')
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    validity_period_start = forms.DateField(required=False)
    validity_period_end = forms.DateField(required=False)

    def __init__(self, *args, **kwargs):
        self.id = kwargs.pop('id')
        super(DocumentsOrderUpdateForm, self).__init__(*args, **kwargs)
        # self.fields["description"].required = False
        self.fields['description'].widget.attrs.update({'class': 'form-control django_ckeditor_5'})
        self.fields['description'].required = False
        self.fields['document_foundation'].queryset = OfficialMemo.objects.filter((Q(order_id=self.id) | Q(order=None)) & Q(docs__isnull=False)).exclude(cancellation=True).exclude(official_memo_type='3')

    class Meta:
        model = DocumentsOrder
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'employee', 'allowed_placed', 'validity_period_start', 'document_order_type', 'description',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name', 'document_foundation')

    # def clean(self):
    #     cleaned_data = super().clean()
    #     scan_file = cleaned_data.get("scan_file")
    #     ext = str(scan_file).split('.')[-1]
    #     if scan_file and ext != 'pdf':
    #         # Сохраняем только если оба поля действительны.
    #         raise ValidationError("Скан документа должен быть в формате PDF")


class PlaceProductionActivityAddForm(forms.ModelForm):
    class Meta:
        model = PlaceProductionActivity
        fields = ('name', 'address', 'short_name')


class PlaceProductionActivityUpdateForm(forms.ModelForm):
    class Meta:
        model = PlaceProductionActivity
        fields = ('name', 'address', 'short_name')


class ReportCardAddForm(forms.ModelForm):
    class Meta:
        model = ReportCard
        fields = ('report_card_day', 'start_time', 'end_time', 'reason_adjustment')

    def clean(self):
        cleaned_data = super().clean()
        report_card_day = cleaned_data.get("report_card_day")
        yesterday = datetime.date.today() - datetime.timedelta(days=3)
        tomorrow = datetime.date.today() + datetime.timedelta(days=2)
        if yesterday > report_card_day or report_card_day > tomorrow:
            raise ValidationError(
                f"Ошибка! Дата может быть только из диапазона c {yesterday.strftime('%d.%m.%Y')} г. "
                f"по {tomorrow.strftime('%d.%m.%Y')} г.")
        start_time = cleaned_data.get("start_time")
        if not start_time:
            raise ValidationError("Ошибка! Не указано время начала!")
        end_time = cleaned_data.get("end_time")
        if not end_time:
            raise ValidationError("Ошибка! Не указано время окончания!")
        if end_time < start_time:
            raise ValidationError("Ошибка! Указан не верный диапазон времени!")
        reason_adjustment = cleaned_data.get("reason_adjustment")
        if reason_adjustment == '':
            raise ValidationError("Ошибка! Причина ручной корректировки не может быть пустой.")


class ReportCardUpdateForm(forms.ModelForm):
    class Meta:
        model = ReportCard
        fields = ('report_card_day', 'start_time', 'end_time', 'reason_adjustment')

    def clean(self):
        cleaned_data = super().clean()
        report_card_day = cleaned_data.get("report_card_day")
        yesterday = datetime.date.today() - datetime.timedelta(days=3)
        tomorrow = datetime.date.today() + datetime.timedelta(days=2)
        if yesterday > report_card_day or report_card_day > tomorrow:
            raise ValidationError(
                f"Ошибка! Дата может быть только из диапазона c {yesterday.strftime('%d.%m.%Y')} г. "
                f"по {tomorrow.strftime('%d.%m.%Y')} г.")
        start_time = cleaned_data.get("start_time")
        if not start_time:
            raise ValidationError("Ошибка! Не указано время начала!")
        end_time = cleaned_data.get("end_time")
        if not end_time:
            raise ValidationError("Ошибка! Не указано время окончания!")
        if end_time < start_time:
            raise ValidationError("Ошибка! Указан не верный диапазон времени!")
        reason_adjustment = cleaned_data.get("reason_adjustment")
        if reason_adjustment == '':
            raise ValidationError("Ошибка! Причина ручной корректировки не может быть пустой.")


class ProvisionsAddForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})


    class Meta:
        model = Provisions
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'storage_location_division', 'employee', 'allowed_placed', 'validity_period_start', 'document_order',
                  'validity_period_end', 'actuality', 'previous_document', 'document_name')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop('user')
        super(ProvisionsAddForm, self).__init__(*args, **kwargs)
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields['employee'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
        self.fields['executor'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})


class ProvisionsUpdateForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = Provisions
        fields = ('executor', 'document_date', 'document_number', 'doc_file', 'scan_file', 'access',
                  'storage_location_division', 'employee', 'validity_period_start', 'validity_period_end', 'previous_document',
                  'allowed_placed', 'actuality', 'document_name', 'document_order')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop('user')
        super(ProvisionsUpdateForm, self).__init__(*args, **kwargs)
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields['employee'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
        self.fields['executor'].widget.attrs.update(
            {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})