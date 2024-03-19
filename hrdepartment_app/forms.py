import datetime

from decouple import config
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from loguru import logger

from customers_app.models import (
    Division,
    DataBaseUser,
    Job,
    HarmfulWorkingConditions,
    AccessLevel,
)
from hrdepartment_app.models import (
    Medical,
    OfficialMemo,
    Purpose,
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
    MedicalOrganisation,
    DocumentsJobDescription,
    DocumentsOrder,
    PlaceProductionActivity,
    ReasonForCancellation,
    OrderDescription,
    ReportCard,
    Provisions, GuidanceDocuments,
)


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


def present_or_future_date(value):
    """
    Проверяет, существует ли дата или находится в будущем.

    :param value: Дата, которую необходимо проверить.
    :return: Исходная дата, если она присутствует или будет в будущем.
    :raises forms.ValidationError: Вызывает исключение если дата в прошлом (более 60 дней назад).
    """
    if value < datetime.date.today() - datetime.timedelta(days=60):
        raise forms.ValidationError("Нельзя использовать прошедшую дату!")
    return value


class MedicalOrganisationAddForm(forms.ModelForm):
    class Meta:
        model = MedicalOrganisation
        fields = ("ref_key", "description", "ogrn", "address", "email", "phone")


class MedicalOrganisationUpdateForm(forms.ModelForm):
    class Meta:
        model = MedicalOrganisation
        fields = ("ref_key", "description", "ogrn", "address", "email", "phone")


class MedicalExaminationAddForm(forms.ModelForm):
    class Meta:
        model = Medical
        fields = ("number", "person", "organisation", "working_status")


class MedicalExaminationUpdateForm(forms.ModelForm):
    harmful = forms.ModelMultipleChoiceField(HarmfulWorkingConditions.objects.all())
    harmful.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )

    class Meta:
        model = Medical
        fields = ("number", "harmful")


class OfficialMemoAddForm(forms.ModelForm):
    memo_type = [
        ("1", "Направление"),
        ("2", "Продление"),
        ("3", "Без выезда"),
    ]
    type_of_trip = [("1", "Служебная поездка"), ("2", "Командировка")]
    place_production_activity = forms.ModelMultipleChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    place_production_activity.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )
    place_departure = forms.ModelChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    place_departure.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all()
        .exclude(is_active=False, username__in=["admin", "proxmox"])
        .order_by("last_name")
    )
    person.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )
    official_memo_type = forms.ChoiceField(choices=memo_type)
    type_trip = forms.ChoiceField(choices=type_of_trip)
    period_from = forms.DateField(label="Дата начала", required=True)
    period_for = forms.DateField(label="Дата окончания", required=True)
    document_extension = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False
    )
    document_extension.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = OfficialMemo
        fields = (
            "period_from",
            "period_for",
            "place_production_activity",
            "place_departure",
            "person",
            "purpose_trip",
            "responsible",
            "type_trip",
            "official_memo_type",
            "document_extension",
            "creation_retroactively",
        )

    def __init__(self, *args, **kwargs):
        super(OfficialMemoAddForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control form-control-modern"
            field.help_text = ""
        self.fields["creation_retroactively"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )

    def date_difference(self, day):
        """
        :param day: Целое число, представляющее количество дней, которое необходимо вычесть из текущей даты.
        :return: Разница в днях между текущей датой и датой, полученной путем вычитания заданного количества дней.
        """
        return datetime.date.today() - datetime.timedelta(days=day)

    def clean(self):
        cleaned_data = super().clean()
        official_memo_type = cleaned_data.get("official_memo_type")
        document_extension = cleaned_data.get("document_extension")
        period_from = cleaned_data.get("period_from")
        period_for = cleaned_data.get("period_for")
        creation_retroactively = cleaned_data.get("creation_retroactively")
        match official_memo_type:
            case "1" | "3":
                if not creation_retroactively:
                    if period_from < self.date_difference(7) or period_for < self.date_difference(7):
                        raise forms.ValidationError(
                            f"Нельзя использовать прошедшую дату! Допустимый период 7 дней. "
                            f"Минимальная дата {self.date_difference(7).strftime('%d.%m.%Y')} г."
                            f"Если все же необходимо завести документ, то установите соответствующий переключатель!"
                        )
            case "2":
                if not document_extension:
                    # Сохраняем только если оба поля действительны.
                    raise ValidationError(
                        "Ошибка создания документа. Для продления необходимо указать документ основания!!!"
                    )
                if not creation_retroactively:
                    if period_from < self.date_difference(7) or period_for < self.date_difference(7):
                        raise forms.ValidationError(
                            f"Нельзя использовать прошедшую дату! Допустимый период 7 дней. "
                            f"Минимальная дата {self.date_difference(7).strftime('%d.%m.%Y')} г."
                            f"Если все же необходимо завести документ, то установите соответствующий переключатель!")


class OfficialMemoUpdateForm(forms.ModelForm):
    type_of = [("1", "Квартира"), ("2", "Гостиница")]
    memo_type = [
        ("1", "Направление"),
        ("2", "Продление"),
        ("3", "Без выезда"),
    ]
    type_of_trip = [("1", "Служебная поездка"), ("2", "Командировка")]
    place_departure = forms.ModelChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    place_departure.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    official_memo_type = forms.ChoiceField(choices=memo_type)
    place_production_activity = forms.ModelMultipleChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    place_production_activity.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    person.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    purpose_trip.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )
    type_trip = forms.ChoiceField(choices=type_of_trip)
    document_extension = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False
    )
    document_extension.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = OfficialMemo
        fields = (
            "person",
            "purpose_trip",
            "period_from",
            "period_for",
            "place_production_activity",
            "comments",
            "type_trip",
            "official_memo_type",
            "place_departure",
            "document_extension",
        )

    def clean(self):
        """
        Этот метод используется для проверки данных, введенных в OfficialMemoUpdateForm. Он проверяет, предшествует ли дата «period_from» дате «period_for».

        :return: None
        """
        # user age must be above 18 to register
        try:
            if self.cleaned_data.get("period_for") < self.cleaned_data.get(
                    "period_from"
            ):
                msg = "Дата начала не может быть больше даты окончания!"
                self.add_error(None, msg)
        except Exception as _ex:
            logger.error(
                f"Ошибка проверки времени: {self.cleaned_data.get('period_for')} {self.cleaned_data.get('period_from')} {_ex}"
            )


class OficialMemoCancelForm(forms.ModelForm):
    # reason_cancellation = forms.ModelChoiceField(queryset=ReasonForCancellation.objects.all(), required=False)
    # reason_cancellation.widget.attrs.update(
    #     {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = OfficialMemo
        fields = ("cancellation", "reason_cancellation")

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.cancel = kwargs.pop("cancel")
        super(OficialMemoCancelForm, self).__init__(*args, **kwargs)
        self.fields["cancellation"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["reason_cancellation"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["reason_cancellation"].required = False

    def clean(self):
        if not self.cancel:
            msg = "Невозможно отменить служебную записку по которой запущен бизнес процесс. Воспользуйтесь отменой записи в документе бизнес процесса."
            self.add_error(None, msg)


class ApprovalOficialMemoProcessAddForm(forms.ModelForm):
    type_of = [("1", "Квартира"), ("2", "Гостиница")]
    # person_executor = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    # person_executor.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    # person_agreement = forms.ModelChoiceField(queryset=DataBaseUser.objects.all(), required=False)
    # person_agreement.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    document = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.filter(docs__isnull=True).exclude(
            cancellation=True
        )
    )
    document.widget.attrs.update(
        {
            "class": "form-control form-control-modern",
            "data-plugin-selectTwo": True,
            "type": "date",
        }
    )

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = (
            "document",
            "person_executor",
            "submit_for_approval",
            "comments_for_approval",
            "person_agreement",
            "start_date_trip",
            "end_date_trip",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop('user')
        super(ApprovalOficialMemoProcessAddForm, self).__init__(*args, **kwargs)
        self.fields["submit_for_approval"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["person_executor"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["person_agreement"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["person_agreement"].required = False


class ApprovalOficialMemoProcessUpdateForm(forms.ModelForm):
    type_of = [("1", "Квартира"), ("2", "Гостиница")]

    person_agreement = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_agreement.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_clerk = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_clerk.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_hr = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_hr.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_distributor = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_distributor.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_department_staff = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_department_staff.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_accounting = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all(), required=False
    )
    person_accounting.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document = forms.ModelChoiceField(queryset=OfficialMemo.objects.all())
    document.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    accommodation = forms.ChoiceField(
        choices=ApprovalOficialMemoProcess.type_of, required=False
    )
    accommodation.widget.attrs.update({"class": "form-control form-control-modern"})
    comments_for_approval = forms.CharField(required=False)
    comments_for_approval.widget.attrs.update(
        {"class": "form-control form-control-modern"}
    )
    reason_for_approval = forms.CharField(required=False)
    prepaid_expense = forms.CharField(required=False)
    reason_for_approval.widget.attrs.update(
        {"class": "form-control form-control-modern"}
    )
    order = forms.ModelChoiceField(
        queryset=DocumentsOrder.objects.all(), required=False
    )
    order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    number_business_trip_days = forms.IntegerField(required=False)
    number_flight_days = forms.IntegerField(required=False)
    prepaid_expense_summ = forms.DecimalField(required=False)

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = (
            "document",
            "person_executor",
            "submit_for_approval",
            "comments_for_approval",
            "person_agreement",
            "document_not_agreed",
            "reason_for_approval",
            "person_distributor",
            "location_selected",
            "person_department_staff",
            "process_accepted",
            "accommodation",
            "order",
            "person_accounting",
            "prepaid_expense",
            "accepted_accounting",
            "person_clerk",
            "originals_received",
            "person_hr",
            "hr_accepted",
            "number_business_trip_days",
            "number_flight_days",
            "start_date_trip",
            "end_date_trip",
            "date_transfer_hr",
            "date_transfer_accounting",
            "date_receipt_original",
            "originals_docs_comment",
            "prepaid_expense_summ",
            "submitted_for_signature",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop('user')
        super(ApprovalOficialMemoProcessUpdateForm, self).__init__(*args, **kwargs)
        self.fields["accepted_accounting"].widget.attrs.update(
            {"class": "mobileToggle"}
        )
        self.fields["hr_accepted"].widget.attrs.update({"class": "mobileToggle"})
        self.fields["originals_received"].widget.attrs.update({"class": "mobileToggle"})
        self.fields["process_accepted"].widget.attrs.update({"class": "mobileToggle"})
        self.fields["location_selected"].widget.attrs.update({"class": "mobileToggle"})
        self.fields["document_not_agreed"].widget.attrs.update(
            {"class": "mobileToggle"}
        )
        self.fields["submit_for_approval"].widget.attrs.update(
            {"class": "mobileToggle"}
        )

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
                if d1[:4] != "(БВ)":
                    raise ValidationError(
                        "Ошибка приема документа делопроизводителем. Приказ не создан!!!"
                    )
        if location_selected:
            if not document_not_agreed:
                raise ValidationError(
                    "Ошибка в назначении места проживания. Документ не согласован руководителем!!!"
                )


class ApprovalOficialMemoProcessChangeForm(forms.ModelForm):
    # reason_cancellation = forms.ModelChoiceField(queryset=ReasonForCancellation.objects.all(), required=False)
    # reason_cancellation.widget.attrs.update(
    #     {'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})

    class Meta:
        model = ApprovalOficialMemoProcess
        fields = ("cancellation", "reason_cancellation")

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        # self.user = kwargs.pop('user')
        super(ApprovalOficialMemoProcessChangeForm, self).__init__(*args, **kwargs)
        self.fields["cancellation"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["reason_cancellation"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["reason_cancellation"].required = False

    def clean(self):
        cleaned_data = super().clean()
        cancellation = cleaned_data.get("cancellation")
        reason_cancellation = cleaned_data.get("reason_cancellation")
        if not cancellation:
            raise ValidationError(
                "Ошибка! Не установлен переключатель отмены документа"
            )
        if not reason_cancellation:
            raise ValidationError("Ошибка! Не выбрана причина отмены")


class BusinessProcessDirectionAddForm(forms.ModelForm):
    type_of = [("1", "SP")]
    business_process_type = forms.ChoiceField(choices=type_of)
    person_agreement = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_agreement.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_executor = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_executor.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    clerk = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    clerk.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_hr = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_hr.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    date_start = forms.DateField(required=False)
    date_end = forms.DateField(required=False)

    class Meta:
        model = BusinessProcessDirection
        fields = "__all__"


class BusinessProcessDirectionUpdateForm(forms.ModelForm):
    type_of = [("1", "SP")]
    business_process_type = forms.ChoiceField(choices=type_of)
    person_agreement = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_agreement.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_executor = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_executor.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    clerk = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    clerk.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    person_hr = forms.ModelMultipleChoiceField(queryset=Job.objects.all())
    person_hr.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    date_start = forms.DateField(required=False)
    date_end = forms.DateField(required=False)

    class Meta:
        model = BusinessProcessDirection
        fields = "__all__"


class PurposeAddForm(forms.ModelForm):
    class Meta:
        model = Purpose
        fields = "__all__"


class PurposeUpdateForm(forms.ModelForm):
    class Meta:
        model = Purpose
        fields = "__all__"


class DocumentsJobDescriptionAddForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    parent_document = forms.ModelChoiceField(queryset=DocumentsJobDescription.objects.all(), required=False)
    parent_document.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = DocumentsJobDescription
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "document_division",
            "employee",
            "allowed_placed",
            "validity_period_start",
            "document_order",
            "validity_period_end",
            "actuality",
            "parent_document",
            "document_name",
            "document_job",
        )


class DocumentsJobDescriptionUpdateForm(forms.ModelForm):
    employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    employee.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())
    document_job.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = DocumentsJobDescription
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "document_division",
            "employee",
            "validity_period_start",
            "validity_period_end",
            "previous_document",
            "allowed_placed",
            "actuality",
            "document_name",
            "document_order",
            "document_job",
        )


type_of_order = [("1", "Общая деятельность"), ("2", "Личный состав")]


class DocumentsOrderAddForm(forms.ModelForm):
    document_foundation = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.filter(Q(order=None) & Q(docs__isnull=False))
        .exclude(cancellation=True)
        .exclude(official_memo_type="3"),
        required=False,
    )
    document_foundation.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_name.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order_type = forms.ChoiceField(choices=type_of_order, label="Тип приказа")
    document_order_type.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    employee = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.all(), label="Ответственные лица"
    )
    employee.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    validity_period_start = forms.DateField(required=False)
    validity_period_end = forms.DateField(required=False)

    class Meta:
        model = DocumentsOrder
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "employee",
            "allowed_placed",
            "validity_period_start",
            "document_order_type",
            "validity_period_end",
            "actuality",
            "previous_document",
            "document_name",
            "document_foundation",
        )

    def clean(self):
        cleaned_data = super().clean()
        scan_file = cleaned_data.get("scan_file")
        ext = str(scan_file).split(".")[-1]
        if scan_file and ext != "pdf":
            # Сохраняем только если оба поля действительны.
            raise ValidationError("Скан документа должен быть в формате PDF")

        document_number = cleaned_data.get("document_number")
        exist_doc = DocumentsOrder.objects.filter()


class DocumentsOrderUpdateForm(forms.ModelForm):
    document_foundation = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False
    )
    document_foundation.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_name.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order_type = forms.ChoiceField(choices=type_of_order)
    document_order_type.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    employee = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.all(), label="Ответственные лица"
    )
    employee.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    validity_period_start = forms.DateField(required=False)
    validity_period_end = forms.DateField(required=False)

    def __init__(self, *args, **kwargs):
        self.id = kwargs.pop("id")
        super(DocumentsOrderUpdateForm, self).__init__(*args, **kwargs)
        # self.fields["description"].required = False
        self.fields["description"].widget.attrs.update(
            {"class": "form-control django_ckeditor_5"}
        )
        # self.fields["document_name"].widget.attrs.update({"class": "form-control form-control-modern", "data-plugin-selectTwo": True})
        self.fields["description"].required = False
        self.fields["document_foundation"].queryset = (
            OfficialMemo.objects.filter(
                (Q(order_id=self.id) | Q(order=None)) & Q(docs__isnull=False)
            )
            .exclude(cancellation=True)
            .exclude(official_memo_type="3")
        )

    class Meta:
        model = DocumentsOrder
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "employee",
            "allowed_placed",
            "validity_period_start",
            "document_order_type",
            "description",
            "validity_period_end",
            "actuality",
            "previous_document",
            "document_name",
            "document_foundation",
        )

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
        fields = ("name", "address", "short_name")


class PlaceProductionActivityUpdateForm(forms.ModelForm):
    class Meta:
        model = PlaceProductionActivity
        fields = ("name", "address", "short_name")


class ReportCardAddForm(forms.ModelForm):
    class Meta:
        model = ReportCard
        fields = ("report_card_day", "start_time", "end_time", "reason_adjustment")

    def clean(self):
        cleaned_data = super().clean()
        report_card_day = cleaned_data.get("report_card_day")
        yesterday = datetime.date.today() - datetime.timedelta(days=7)
        tomorrow = datetime.date.today() + datetime.timedelta(days=2)
        if yesterday > report_card_day or report_card_day > tomorrow:
            raise ValidationError(
                f"Ошибка! Дата может быть только из диапазона c {yesterday.strftime('%d.%m.%Y')} г. "
                f"по {tomorrow.strftime('%d.%m.%Y')} г."
            )
        start_time = cleaned_data.get("start_time")
        if not start_time:
            raise ValidationError("Ошибка! Не указано время начала!")
        end_time = cleaned_data.get("end_time")
        if not end_time:
            raise ValidationError("Ошибка! Не указано время окончания!")
        if end_time < start_time:
            raise ValidationError("Ошибка! Указан не верный диапазон времени!")
        reason_adjustment = cleaned_data.get("reason_adjustment")
        if reason_adjustment == "":
            raise ValidationError(
                "Ошибка! Причина ручной корректировки не может быть пустой."
            )


class ReportCardUpdateForm(forms.ModelForm):
    class Meta:
        model = ReportCard
        fields = ("report_card_day", "start_time", "end_time", "reason_adjustment")

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(ReportCardUpdateForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        report_card_day = cleaned_data.get("report_card_day")
        yesterday = datetime.date.today() - datetime.timedelta(days=7)
        tomorrow = datetime.date.today() + datetime.timedelta(days=2)
        user_obj = DataBaseUser.objects.get(pk=self.user)
        if not user_obj.is_superuser:
            if yesterday > report_card_day or report_card_day > tomorrow:
                raise ValidationError(
                    f"Ошибка! Дата может быть только из диапазона c {yesterday.strftime('%d.%m.%Y')} г. "
                    f"по {tomorrow.strftime('%d.%m.%Y')} г."
                )
        start_time = cleaned_data.get("start_time")
        if not start_time:
            raise ValidationError("Ошибка! Не указано время начала!")
        end_time = cleaned_data.get("end_time")
        if not end_time:
            raise ValidationError("Ошибка! Не указано время окончания!")
        if end_time < start_time:
            raise ValidationError("Ошибка! Указан не верный диапазон времени!")
        reason_adjustment = cleaned_data.get("reason_adjustment")
        if reason_adjustment == "":
            raise ValidationError(
                "Ошибка! Причина ручной корректировки не может быть пустой."
            )


class ProvisionsAddForm(forms.ModelForm):
    # employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    # employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Provisions
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "employee",
            "allowed_placed",
            "validity_period_start",
            "document_order",
            "validity_period_end",
            "actuality",
            "previous_document",
            "document_name",
            "document_form",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(ProvisionsAddForm, self).__init__(*args, **kwargs)
        self.fields["executor"].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["document_form"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["document_form"].required = False
        self.fields["executor"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["applying_for_job"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )


class ProvisionsUpdateForm(forms.ModelForm):
    # employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    # employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Provisions
        fields = (
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "employee",
            "validity_period_start",
            "validity_period_end",
            "previous_document",
            "allowed_placed",
            "actuality",
            "document_name",
            "document_order",
            "document_form",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(ProvisionsUpdateForm, self).__init__(*args, **kwargs)
        # self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["document_form"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["document_form"].required = False
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["applying_for_job"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )


class OrderDescriptionForm(forms.ModelForm):
    """
    Форма для создания или обновления экземпляра OrderDescription.

    Поля:
        - name: CharField
        - affiliation: CharField

    Методы:
        clean_name: проверка поле «name».
    """

    class Meta:
        model = OrderDescription
        fields = ["name", "affiliation"]

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise forms.ValidationError("Это поле не может быть пустым.")
        # Add more validations if needed
        return name


class GuidanceDocumentsAddForm(forms.ModelForm):
    # employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    # employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = GuidanceDocuments
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "employee",
            "allowed_placed",
            "validity_period_start",
            "document_order",
            "validity_period_end",
            "actuality",
            "previous_document",
            "document_name",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(GuidanceDocumentsAddForm, self).__init__(*args, **kwargs)
        self.fields["executor"].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["executor"].widget.attrs.update(
            {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        )
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["applying_for_job"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )


class GuidanceDocumentsUpdateForm(forms.ModelForm):
    # employee = forms.ModelMultipleChoiceField(queryset=DataBaseUser.objects.all())
    # employee.widget.attrs.update({'class': 'form-control form-control-modern', 'data-plugin-selectTwo': True})
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_order.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = GuidanceDocuments
        fields = (
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "employee",
            "validity_period_start",
            "validity_period_end",
            "previous_document",
            "allowed_placed",
            "actuality",
            "document_name",
            "document_order",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(GuidanceDocumentsUpdateForm, self).__init__(*args, **kwargs)
        # self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
        self.fields["employee"].widget.attrs.update(
            {
                "class": "form-control form-control-modern",
                "data-plugin-multiselect": True,
                "multiple": "multiple",
                "data-plugin-options": '{ "maxHeight": 200, "includeSelectAllOption": true }',
            }
        )
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["applying_for_job"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
