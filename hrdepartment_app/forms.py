import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from core import logger
from administration_app.utils import make_custom_field
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
    OrderDescription,
    ReportCard,
    Provisions, GuidanceDocuments, CreatingTeam, TimeSheet, OutfitCard, Briefings,
    Operational, DataBaseUserEvent, BusinessProcessRoutes, LaborProtection,
)


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
            "expenses_summ",
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
            "expenses_summ"
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
        # self.fields["submit_for_approval"].widget.attrs.update(
        #     {"class": "todo-check", "data-plugin-ios-switch": True}
        # )
        # self.fields["person_executor"].widget.attrs.update(
        #     {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        # )
        # self.fields["person_agreement"].widget.attrs.update(
        #     {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
        # )
        self.fields["person_agreement"].required = False
        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean(self):
        if not self.cleaned_data.get("submit_for_approval"):
            raise ValidationError(
                "Невозможно запустить бизнес процесс. Не установлен переключатель передачи на согласование.")


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
    class Meta:
        model = BusinessProcessDirection
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        self.fields["clerk"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        for field in self.fields:
            make_custom_field(self.fields[field])


class BusinessProcessDirectionUpdateForm(forms.ModelForm):
    class Meta:
        model = BusinessProcessDirection
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        self.fields["clerk"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        for field in self.fields:
            make_custom_field(self.fields[field])


class BusinessProcessRoutesAddForm(forms.ModelForm):
    class Meta:
        model = BusinessProcessRoutes
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_clerk"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_sd"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_accounting"].widget.attrs.update({"multiple": "multiple", })
        for field in self.fields:
            make_custom_field(self.fields[field])


class BusinessProcessRoutesUpdateForm(forms.ModelForm):
    class Meta:
        model = BusinessProcessRoutes
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_clerk"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_sd"].widget.attrs.update({"multiple": "multiple", })
        self.fields["person_accounting"].widget.attrs.update({"multiple": "multiple", })
        for field in self.fields:
            make_custom_field(self.fields[field])


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
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    document_order = forms.ModelChoiceField(queryset=DocumentsOrder.objects.all())
    document_division = forms.ModelChoiceField(queryset=Division.objects.all())
    document_job = forms.ModelChoiceField(queryset=Job.objects.all())

    class Meta:
        model = DocumentsJobDescription
        fields = (
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
            "parent_document",
            "document_order",
            "document_job",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


type_of_order = [("1", "Общая деятельность"), ("2", "Личный состав")]


class DocumentsOrderAddForm(forms.ModelForm):
    document_foundation = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.filter(Q(order=None) & Q(docs__isnull=False))
        .exclude(cancellation=True)
        .exclude(official_memo_type="3"),
        required=False,
    )
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_order_type = forms.ChoiceField(choices=type_of_order, label="Тип приказа")
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    employee = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.all(), label="Ответственные лица"
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

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
    document_name = forms.ModelChoiceField(queryset=OrderDescription.objects.all())
    document_order_type = forms.ChoiceField(choices=type_of_order)
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    employee = forms.ModelMultipleChoiceField(
        queryset=DataBaseUser.objects.all(), label="Ответственные лица"
    )
    validity_period_start = forms.DateField(required=False)
    validity_period_end = forms.DateField(required=False)

    def __init__(self, *args, **kwargs):
        self.id = kwargs.pop("id")
        super().__init__(*args, **kwargs)
        # self.fields["description"].required = False
        self.fields["description"].widget.attrs.update(
            {"class": "form-control django_ckeditor_5"}
        )
        self.fields["description"].required = False
        self.fields["document_foundation"].queryset = (
            OfficialMemo.objects.filter(
                (Q(order_id=self.id) | Q(order=None)) & Q(docs__isnull=False)
            )
            .exclude(cancellation=True)
            .exclude(official_memo_type="3")
        )
        for field in self.fields:
            make_custom_field(self.fields[field])

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
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class PlaceProductionActivityUpdateForm(forms.ModelForm):
    class Meta:
        model = PlaceProductionActivity
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class ReportCardAddForm(forms.ModelForm):
    class Meta:
        model = ReportCard
        fields = ("report_card_day", "start_time", "end_time", "reason_adjustment")

    def clean(self):
        cleaned_data = super().clean()
        report_card_day = cleaned_data.get("report_card_day")
        yesterday = datetime.date.today() - datetime.timedelta(days=10)
        tomorrow = datetime.date.today() + datetime.timedelta(days=4)
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
        yesterday = datetime.date.today() - datetime.timedelta(days=10)
        tomorrow = datetime.date.today() + datetime.timedelta(days=4)
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
            "parent_document",
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
        for field in self.fields:
            make_custom_field(self.fields[field])


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
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "employee",
            "validity_period_start",
            "validity_period_end",
            "parent_document",
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
        self.fields['executor'].queryset = DataBaseUser.objects.filter(pk=self.user)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class BriefingsAddForm(forms.ModelForm):
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
        model = Briefings
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
            "parent_document",
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
        super(BriefingsAddForm, self).__init__(*args, **kwargs)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class BriefingsUpdateForm(forms.ModelForm):
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
        model = Briefings
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
            "parent_document",
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
        super(BriefingsUpdateForm, self).__init__(*args, **kwargs)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class OperationalAddForm(forms.ModelForm):
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Operational
        fields = (
            "executor",
            "document_date",
            "document_number",
            "scan_file",
            "storage_location_division",
            "allowed_placed",
            "validity_period_start",
            "validity_period_end",
            "actuality",
            "parent_document",
            "document_name",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(OperationalAddForm, self).__init__(*args, **kwargs)
        self.fields["executor"].queryset = DataBaseUser.objects.filter(pk=self.user)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class OperationalUpdateForm(forms.ModelForm):
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = Operational
        fields = (
            "document_date",
            "document_number",
            "scan_file",
            "storage_location_division",
            "validity_period_start",
            "validity_period_end",
            "parent_document",
            "allowed_placed",
            "actuality",
            "document_name",
            "applying_for_job",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(OperationalUpdateForm, self).__init__(*args, **kwargs)
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["applying_for_job"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])


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


class CreatingTeamAddForm(forms.ModelForm):
    class Meta:
        model = CreatingTeam
        fields = ('senior_brigade', 'team_brigade', 'executor_person', 'approving_person', 'date_start', 'date_end',
                  'place', 'date_create', 'company_property', 'replaceable_document', 'document_type')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        approving_person_list = [item['person_agreement'] for item in
                                 BusinessProcessRoutes.objects.filter(business_process_type=2).values(
                                     'person_agreement')]
        person_executor_list = [item['person_executor'] for item in
                                BusinessProcessRoutes.objects.filter(business_process_type=2).values(
                                    'person_executor')]
        super(CreatingTeamAddForm, self).__init__(*args, **kwargs)
        self.fields['approving_person'].queryset = DataBaseUser.objects.filter(
            pk__in=approving_person_list).exclude(is_active=False)
        self.fields["executor_person"].queryset = DataBaseUser.objects.filter(
            pk__in=person_executor_list).exclude(is_active=False)
        self.fields['place'].queryset = PlaceProductionActivity.objects.filter(use_team_orders=True)
        self.fields["senior_brigade"].queryset = DataBaseUser.objects.filter(
            user_work_profile__job__division_affiliation__name='Инженерный состав').exclude(is_active=False)
        self.fields["team_brigade"].queryset = DataBaseUser.objects.filter(
            user_work_profile__job__division_affiliation__name='Инженерный состав').exclude(is_active=False)
        self.fields["team_brigade"].widget.attrs.update({"multiple": "multiple"})
        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean(self):
        cleaned_data = super(CreatingTeamAddForm, self).clean()
        executor_person = cleaned_data.get("executor_person")

        if executor_person.pk != self.user:
            raise ValidationError(
                "Ошибка! Вы не входите в список лиц, кому разрешено создание приказов о старших бригадах."
            )

        return cleaned_data


class CreatingTeamUpdateForm(forms.ModelForm):
    class Meta:
        model = CreatingTeam
        fields = ('senior_brigade', 'team_brigade', 'executor_person', 'approving_person', 'date_start', 'date_end',
                  'place', 'date_create', 'number', 'company_property', 'scan_file')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        # Выбрать из списка бизнес-процессов имеющих право согласования
        approving_person_list = [item['person_agreement'] for item in
                                 BusinessProcessRoutes.objects.filter(business_process_type=2).values(
                                     'person_agreement')]
        person_executor_list = [item['person_executor'] for item in
                                BusinessProcessRoutes.objects.filter(business_process_type=2).values(
                                    'person_executor')]
        super(CreatingTeamUpdateForm, self).__init__(*args, **kwargs)
        self.fields["executor_person"].queryset = DataBaseUser.objects.filter(
            pk__in=person_executor_list).exclude(is_active=False)
        self.fields['approving_person'].queryset = DataBaseUser.objects.filter(
            pk__in=approving_person_list).exclude(is_active=False)
        self.fields['place'].queryset = PlaceProductionActivity.objects.filter(use_team_orders=True)
        self.fields["senior_brigade"].queryset = DataBaseUser.objects.filter(
            user_work_profile__job__division_affiliation__name='Инженерный состав').exclude(is_active=False)
        self.fields["team_brigade"].queryset = DataBaseUser.objects.filter(
            user_work_profile__job__division_affiliation__name='Инженерный состав').exclude(is_active=False)
        self.fields["team_brigade"].widget.attrs.update({"multiple": "multiple"})
        for field in self.fields:
            make_custom_field(self.fields[field])


class CreatingTeamAgreedForm(forms.ModelForm):
    class Meta:
        model = CreatingTeam
        fields = ('agreed',)

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        self.approving_person = kwargs.pop("approving_person")
        super(CreatingTeamAgreedForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_agreed(self):
        agreed = self.cleaned_data.get("agreed")
        if not agreed:
            return agreed
        if self.user in self.approving_person:
            return agreed
        else:
            raise ValidationError("Ошибка! Вы не имеете право согласования приказов о старших бригадах.")


class CreatingTeamSetNumberForm(forms.ModelForm):
    class Meta:
        model = CreatingTeam
        fields = ('number', 'scan_file')

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        self.hr_person = kwargs.pop("hr_person")
        super(CreatingTeamSetNumberForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean_number(self):
        number = self.cleaned_data.get("number")
        if number == '':
            return number
        if self.user in self.hr_person:
            return number
        else:
            raise ValidationError("Ошибка! Вы не имеете право задавать номера приказов о старших бригадах.")


class TimeSheetForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        widget=forms.Select(attrs={"class": "form-control form-control-modern",
                                   "data-plugin-selectTwo": True, }),
        queryset=DataBaseUser.objects.filter(is_active=True),
        label="Сотрудник")

    class Meta:
        model = TimeSheet
        fields = ['date', 'employee', 'time_sheets_place', 'notes']
        # widgets = {
        #     'date': forms.DateInput(attrs={"class": "form-control form-control-modern",
        #                                    "data-plugin-datepicker": True,
        #                                    "type": "date",
        #                                    "data-date-language": "ru",
        #                                    "todayBtn": True,
        #                                    "clearBtn": True,
        #                                    "data-plugin-options": '{"orientation": "bottom", "format": "dd.mm.yyyy"}', }),
        #     'employee': forms.Select(attrs={"class": "form-control form-control-modern",
        #                                     "data-plugin-selectTwo": True, }),
        #     'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 1}),
        #     'time_sheets_place': forms.Select(attrs={"class": "form-control form-control-modern",
        #                                              "data-plugin-selectTwo": True, }),
        # }

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        super(TimeSheetForm, self).__init__(*args, **kwargs)

        for field in self.fields:
            make_custom_field(self.fields[field])


class ReportCardForm(forms.ModelForm):
    outfit_card = forms.ModelMultipleChoiceField(
        queryset=OutfitCard.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "data-plugin-selectTwo": True, "multiple": True}),
        required=False,
        label="Карта-наряд"
    )
    employee = forms.ModelChoiceField(
        widget=forms.Select(attrs={"class": "form-control form-control-modern"}),
        queryset=DataBaseUser.objects.filter(is_active=True),
        label="Сотрудник")

    start_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-modern'}),
        label="Время начала"
    )

    end_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-modern'}),
        label="Время окончания"
    )

    class Meta:
        model = ReportCard
        fields = ['employee', 'start_time', 'end_time', 'lunch_time', 'flight_hours', 'outfit_card', 'additional_work']
        widgets = {
            'employee': forms.Select(attrs={"class": "form-control form-control-modern"}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-modern'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-modern'}),
            'lunch_time': forms.TextInput(attrs={'type': 'number', 'class': 'form-control form-control-modern', }),
            'flight_hours': forms.TextInput(attrs={'type': 'number', 'class': 'form-control form-control-modern', }),
            'additional_work': forms.TextInput(attrs={'type': 'text', 'class': 'form-control form-control-modern', }),
        }


class OutfitCardForm(forms.ModelForm):
    outfit_card_place = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.filter(use_team_orders=True),
                                               label="МПД")
    employee = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(user_work_profile__job__division_affiliation__name="Инженерный состав"),
        label="Сотрудник")

    class Meta:
        model = OutfitCard
        fields = ['outfit_card_date', 'outfit_card_number', 'employee', 'outfit_card_place',
                  'air_board', 'operational_work', 'periodic_work', 'other_work', 'notes', 'scan_document',
                  'outfit_card_date_end']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(OutfitCardForm, self).__init__(*args, **kwargs)
        place = CreatingTeam.objects.filter(senior_brigade=self.user).exclude(cancellation=True).values_list(
            'date_start', 'date_end', 'place', )
        self.fields["employee"].queryset = DataBaseUser.objects.none()
        self.fields["outfit_card_place"].queryset = PlaceProductionActivity.objects.none()
        for item in place:
            if item[0] <= datetime.date.today() <= item[1]:
                self.fields["employee"].queryset = DataBaseUser.objects.filter(pk=self.user.pk)
                self.fields["outfit_card_place"].queryset = PlaceProductionActivity.objects.filter(pk=item[2])
        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean(self):
        cleaned_data = super(OutfitCardForm, self).clean()
        if cleaned_data['outfit_card_date_end']:
            if cleaned_data['outfit_card_date'] > cleaned_data['outfit_card_date_end']:
                raise ValidationError("Дата окончания должна быть больше чем дата начала")


class DataBaseUserEventAddForm(forms.ModelForm):
    place = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.filter(use_team_orders=True))
    place.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = DataBaseUserEvent
        fields = (
            "person",
            "date_marks",
            "place",
            "checked",
            "road",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(DataBaseUserEventAddForm, self).__init__(*args, **kwargs)
        self.fields["person"].queryset = DataBaseUser.objects.filter(pk=self.user)

        self.fields["checked"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["road"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])


class DataBaseUserEventUpdateForm(forms.ModelForm):
    place = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.filter(use_team_orders=True))
    place.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = DataBaseUserEvent
        fields = (
            "person",
            "date_marks",
            "place",
            "checked",
            "road",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(DataBaseUserEventUpdateForm, self).__init__(*args, **kwargs)
        self.fields["person"].queryset = DataBaseUser.objects.filter(pk=self.user)

        self.fields["checked"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["road"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])


class LaborProtectionAddForm(forms.ModelForm):
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
        model = LaborProtection
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
            "parent_document",
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
        super(LaborProtectionAddForm, self).__init__(*args, **kwargs)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class LaborProtectionUpdateForm(forms.ModelForm):
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
        model = LaborProtection
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
            "parent_document",
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
        super(LaborProtectionUpdateForm, self).__init__(*args, **kwargs)
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
        for field in self.fields:
            make_custom_field(self.fields[field])
