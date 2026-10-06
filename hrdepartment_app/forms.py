import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from decouple import config
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Q

from contracts_app.models import Contract, Estate
from core import logger
from administration_app.utils import make_custom_field
from django.utils import timezone
from customers_app.models import (
    Division,
    DataBaseUser,
    Job,
    HarmfulWorkingConditions,
    AccessLevel, Apartments, DataBaseUserWorkProfile,
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
    Operational, DataBaseUserEvent, BusinessProcessRoutes, LaborProtection, LaborProtectionInstructions,
    StudentAgreement, TrainingProgram, TrainingUnit, PowerOfAttorney, PeriodicWork, OperationalWork,
    AircraftHoursTracking, HoursTrackingSource, MaintenanceReleaseCertificate,
    MaintenanceEquipment, EquipmentOperationalStatus, EquipmentVerificationType, OutfitCardEquipmentUsage,
    EquipmentVerificationRecord, EquipmentName, EquipmentTypeModel, EquipmentTransferRequest, EquipmentTransferStatus,
    MaintenanceWorkEquipmentRequirement,
)

# Дата начала применения валидации
VALIDATION_START_DATE = datetime.datetime.strptime(config("VALIDATION_START_DATE", default="2026-04-01"),
                                                   "%Y-%m-%d").date()


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
    """Форма добавления медицинского направления.

    Включает выбор сотрудника, медицинской организации, статуса (работающий / поступающий),
    вида осмотра (медицинский осмотр / психиатрическое освидетельствование) и типа осмотра
    (предварительный, периодический, внеплановый).
    """

    class Meta:
        model = Medical
        fields = (
            "number",
            "person",
            "organisation",
            "working_status",
            "view_inspection",
            "type_inspection",
        )
        widgets = {
            "number": forms.TextInput(
                attrs={"class": "form-control form-control-modern font-weight-bold", "placeholder": "Номер направления"}
            ),
            "person": forms.Select(
                attrs={"class": "form-control form-control-modern data-plugin-selectTwo", "data-plugin-selectTwo": True}
            ),
            "organisation": forms.Select(
                attrs={"class": "form-control form-control-modern data-plugin-selectTwo", "data-plugin-selectTwo": True}
            ),
            "working_status": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
            "view_inspection": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
            "type_inspection": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
        }


class MedicalExaminationUpdateForm(forms.ModelForm):
    """Форма редактирования медицинского направления.

    Позволяет изменять номер направления, статус, вид осмотра, тип осмотра,
    а также список вредных производственных факторов с автогенерацией документов.
    """

    harmful = forms.ModelMultipleChoiceField(
        queryset=HarmfulWorkingConditions.objects.all(),
        required=False,
        label="Вредные условия труда",
    )
    harmful.widget.attrs.update(
        {
            "class": "form-control form-control-modern data-plugin-selectTwo",
            "data-plugin-selectTwo": True,
        }
    )

    class Meta:
        model = Medical
        fields = (
            "number",
            "working_status",
            "view_inspection",
            "type_inspection",
            "harmful",
        )
        widgets = {
            "number": forms.TextInput(
                attrs={"class": "form-control form-control-modern font-weight-bold", "placeholder": "Номер направления"}
            ),
            "working_status": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
            "view_inspection": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
            "type_inspection": forms.Select(
                attrs={"class": "form-control form-control-modern"}
            ),
        }


class OfficialMemoAddForm(forms.ModelForm):
    """Форма создания новой служебной записки на служебную поездку или командировку.

    Поддерживает выбор сотрудника, типа поездки, дат, места назначения и отправления,
    расчет аванса, а также флаг ретроспективного ввода (задним числом).
    """

    memo_type = [
        ("1", "Направление"),
        ("2", "Продление"),
        ("3", "Без выезда"),
    ]
    type_of_trip = [("1", "Служебная поездка"), ("2", "Командировка")]
    place_production_activity = forms.ModelMultipleChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    place_departure = forms.ModelChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    person = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.all()
        .exclude(is_active=False, username__in=["admin", "proxmox"])
        .order_by("last_name")
    )
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    official_memo_type = forms.ChoiceField(choices=memo_type)
    type_trip = forms.ChoiceField(choices=type_of_trip)
    period_from = forms.DateField(label="Дата начала", required=True)
    period_for = forms.DateField(label="Дата окончания", required=True)
    document_extension = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False
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
        """Инициализирует форму и настраивает стилизацию виджетов.

        Args:
            *args: Позиционные аргументы конструктора формы.
            **kwargs: Именованные аргументы конструктора формы.
        """
        super(OfficialMemoAddForm, self).__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control form-control-modern"
            field.help_text = ""
        self.fields["creation_retroactively"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["place_production_activity"].widget.attrs.update(
            {"class": "form-control form-control-modern",
             "data-plugin-selectTwo": "true", }
        )
        excluded_fields = ['place_production_activity', ]  # список полей для исключения

        for field in self.fields:
            if field not in excluded_fields:
                make_custom_field(self.fields[field])

    def date_difference(self, day: int) -> datetime.date:
        """Вычисляет дату со смещением на заданное количество дней назад от текущей.

        Args:
            day (int): Количество дней для вычитания из текущей даты.

        Returns:
            datetime.date: Рассчитанная календарная дата.
        """
        return datetime.date.today() - datetime.timedelta(days=day)

    def clean(self) -> Dict[str, Any]:
        """Выполняет валидацию данных формы создания служебной записки.

        Проверяет корректность указания документа основания при продлении,
        допустимость выбора прошедших дат (не старше 7 дней, если не установлен
        переключатель creation_retroactively), и непротиворечивость диапазона дат.

        Returns:
            Dict[str, Any]: Словарь очищенных данных формы.

        Raises:
            forms.ValidationError: Если нарушены бизнес-правила дат или продления.
        """
        cleaned_data = super().clean()
        official_memo_type = cleaned_data.get("official_memo_type")
        document_extension = cleaned_data.get("document_extension")
        period_from = cleaned_data.get("period_from")
        period_for = cleaned_data.get("period_for")
        creation_retroactively = cleaned_data.get("creation_retroactively")
        person = cleaned_data.get("person")

        # 1. Сначала выполняем ваши базовые проверки типов и ретроспективного ввода
        match official_memo_type:
            case "1" | "3":
                if not creation_retroactively:
                    if (period_from and period_from < self.date_difference(7)) or (
                            period_for and period_for < self.date_difference(7)):
                        raise forms.ValidationError(
                            f"Нельзя использовать прошедшую дату! Допустимый период 7 дней. "
                            f"Минимальная дата {self.date_difference(7).strftime('%d.%m.%Y')} г."
                            f"Если все же необходимо завести документ, то установите соответствующий переключатель!"
                        )
            case "2":
                if not document_extension:
                    raise forms.ValidationError(
                        "Ошибка создания документа. Для продления необходимо указать документ основания!!!"
                    )
                if not creation_retroactively:
                    if (period_from and period_from < self.date_difference(7)) or (
                            period_for and period_for < self.date_difference(7)):
                        raise forms.ValidationError(
                            f"Нельзя использовать прошедшую дату! Допустимый период 7 дней. "
                            f"Минимальная дата {self.date_difference(7).strftime('%d.%m.%Y')} г."
                            f"Если все же необходимо завести документ, то установите соответствующий переключатель!"
                        )

        # 2. Проверка: Дата начала не должна быть больше даты окончания (базовый логический баг)
        if period_from and period_for:
            if period_for < period_from:
                raise forms.ValidationError("Дата начала не может быть больше даты окончания!")

        # # 3. Проверка пересечения дат для сотрудника
        # if person and period_from and period_for and person.user_work_profile.job.type_of_job == "2":
        #     # Ищем существующие активные поездки сотрудника, которые пересекаются по датам
        #     overlapping_memos = OfficialMemo.objects.filter(
        #         person=person,
        #         cancellation=False,  # Исключаем отмененные служебные записки
        #         period_from__lte=period_for,  # Существующая начинается раньше или в день окончания новой
        #         period_for__gte=period_from  # Существующая заканчивается позже или в день начала новой
        #     )
        #
        #     if overlapping_memos.exists():
        #         conflict_memo = overlapping_memos.first()
        #         conflict_start = conflict_memo.period_from.strftime("%d.%m.%Y")
        #         conflict_end = conflict_memo.period_for.strftime("%d.%m.%Y")
        #
        #         raise forms.ValidationError(
        #             f"Сотрудник уже находится в служебной поездке в указанный период! "
        #             f"Обнаружено пересечение с документом от {conflict_start} по {conflict_end}. "
        #             f"Пожалуйста, сместите сроки новой поездки."
        #         )

        return cleaned_data


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
    official_memo_type = forms.ChoiceField(choices=memo_type)
    place_production_activity = forms.ModelMultipleChoiceField(
        queryset=PlaceProductionActivity.objects.all()
    )
    person = forms.ModelChoiceField(queryset=DataBaseUser.objects.all())
    purpose_trip = forms.ModelChoiceField(queryset=Purpose.objects.all())
    type_trip = forms.ChoiceField(choices=type_of_trip)
    document_extension = forms.ModelChoiceField(
        queryset=OfficialMemo.objects.all(), required=False
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

    def __init__(self, *args, **kwargs):
        super(OfficialMemoUpdateForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])

    # def clean(self):
    #     """
    #     Этот метод используется для проверки данных, введенных в OfficialMemoUpdateForm. Он проверяет, предшествует ли дата «period_from» дате «period_for».
    #
    #     :return: None
    #     """
    #     # user age must be above 18 to register
    #     try:
    #         if self.cleaned_data.get("period_for") < self.cleaned_data.get(
    #                 "period_from"
    #         ):
    #             msg = "Дата начала не может быть больше даты окончания!"
    #             self.add_error(None, msg)
    #     except Exception as _ex:
    #         logger.error(
    #             f"Ошибка проверки времени: {self.cleaned_data.get('period_for')} {self.cleaned_data.get('period_from')} {_ex}"
    #         )

    def clean(self):
        """Этот метод используется для проверки данных, введенных в OfficialMemoUpdateForm.

        Он проверяет, предшествует ли дата «period_from» дате «period_for»,
        а также проверяет отсутствие пересечений дат поездок для выбранного сотрудника.
        """
        cleaned_data = super().clean()

        period_from = cleaned_data.get("period_from")
        period_for = cleaned_data.get("period_for")
        person = cleaned_data.get("person")

        # 1. Базовая проверка: Дата начала не может быть позже даты окончания
        if period_from and period_for:
            if period_for < period_from:
                msg = "Дата начала не может быть больше даты окончания!"
                self.add_error("period_from", msg)

        # 2. Проверка пересечения дат для сотрудника
        if person and period_from and period_for and person.user_work_profile.job.type_of_job == "2":
            try:
                # Строим запрос на пересечение интервалов:
                # Существующая поездка начинается раньше или в день окончания новой
                # И существующая поездка заканчивается позже или в день начала новой
                overlapping_memos = OfficialMemo.objects.filter(
                    person=person,
                    cancellation=False,  # Исключаем отмененные записки, если нужно
                    period_from__lte=period_for,
                    period_for__gte=period_from,
                )
                print(person, period_for, period_from, overlapping_memos)
                # Если мы редактируем существующий документ (в kwargs передан instance),
                # исключаем его из результатов поиска, чтобы он не пересекался сам с собой
                if self.instance and self.instance.pk:
                    overlapping_memos = overlapping_memos.exclude(
                        pk=self.instance.pk
                    )

                # Если нашли хотя бы одно пересечение
                if overlapping_memos.exists():
                    # Возьмем первую попавшуюся для вывода информации в ошибке
                    conflict_memo = overlapping_memos.first()
                    conflict_start = conflict_memo.period_from.strftime("%d.%m.%Y")
                    conflict_end = conflict_memo.period_for.strftime("%d.%m.%Y")

                    msg = (
                        f"Сотрудник уже находится в служебной поездке в этот период! "
                        f"Обнаружено пересечение с документом от {conflict_start} по {conflict_end}. "
                        f"Пожалуйста, сместите сроки новой поездки."
                    )

                    # Добавляем ошибку ко всей форме (non-field error)
                    self.add_error(None, msg)

            except Exception as _ex:
                logger.error(
                    f"Ошибка проверки пересечения дат: "
                    f"сотрудник={person.id if person else None}, "
                    f"с {period_from} по {period_for}. Ошибка: {_ex}"
                )

        return cleaned_data

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
    daily_allowance = forms.DecimalField(required=False)
    travel_expense = forms.DecimalField(required=False)
    accommodation_expense = forms.DecimalField(required=False)
    other_expense = forms.DecimalField(required=False)

    apartment = forms.ModelChoiceField(
        queryset=Apartments.objects.none(),  # Будет заполнено в __init__
        required=False,
        label="Квартира"
    )
    apartment.widget.attrs.update({
        "class": "form-control form-control-modern",
        "data-plugin-selectTwo": True
    })

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
            "apartment",  # Добавляем поле
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
            "daily_allowance",
            "travel_expense",
            "accommodation_expense",
            "other_expense",
            "date_of_arrival",
            "date_of_departure"
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
        # Если есть экземпляр, подгружаем данные
        if self.instance.pk and self.instance.document and self.instance.check_apart:
            doc = self.instance.document
            first_mpd = doc.place_production_activity.first()

            # 1. Определяем текущую квартиру из бронирования
            current_apartment = None
            if hasattr(self.instance, 'apartment_booking') and self.instance.apartment_booking:
                current_apartment = self.instance.apartment_booking.apartment

            if first_mpd and doc.period_from and doc.period_for:
                # 2. Показываем ВСЕ квартиры МПД (не только свободные)
                all_apartments = Apartments.objects.filter(place=first_mpd)

                # 3. Формируем queryset со всеми квартирами
                self.fields["apartment"].queryset = all_apartments

                # 4. Если есть текущая бронь, устанавливаем её как начальное значение
                if current_apartment:
                    self.fields["apartment"].initial = current_apartment.pk

                # 5. Добавляем информацию о занятости в label каждой квартиры
                # Это будет отображаться в выпадающем списке
                apartment_choices = []
                for apt in all_apartments:
                    available_beds = apt.get_available_beds(
                        doc.period_from,
                        doc.period_for,
                        exclude_process=self.instance
                    )
                    if available_beds > 0:
                        label = f"{apt} (свободно: {available_beds}/{apt.beds_number})"
                    else:
                        label = f"{apt} (ЗАНЯТО на этот период)"
                    apartment_choices.append((apt.pk, label))

                # Обновляем choices для отображения в форме
                self.fields["apartment"].choices = [('', '---------')] + apartment_choices
            else:
                if current_apartment:
                    self.fields["apartment"].queryset = Apartments.objects.filter(pk=current_apartment.pk)
                    self.fields["apartment"].initial = current_apartment.pk
                else:
                    self.fields["apartment"].queryset = Apartments.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        person_agreement = cleaned_data.get("person_agreement")
        document_not_agreed = cleaned_data.get("document_not_agreed")
        person_distributor = cleaned_data.get("person_distributor")
        location_selected = cleaned_data.get("location_selected")
        accommodation = cleaned_data.get("accommodation")
        apartment = cleaned_data.get("apartment")
        person_department_staff = cleaned_data.get("person_department_staff")
        process_accepted = cleaned_data.get("process_accepted")
        order = cleaned_data.get("order")
        d1 = str(cleaned_data.get("document"))
        document = cleaned_data.get("document")
        originals_received = cleaned_data.get("originals_received")

        if not person_agreement and document_not_agreed:
            # Сохраняем только если оба поля действительны.
            raise ValidationError(
                "Ошибка согласования документа. Поле руководителя не заполнено!!!"
            )
        if (not person_distributor or not accommodation) and location_selected:
            # Сохраняем только если оба поля действительны.
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

        # Проверяем, применяется ли валидация (только с 1 марта 2026)
        validation_applies = False
        if document and document.period_from:
            validation_applies = document.period_from >= VALIDATION_START_DATE

        # Если выбрана квартира, должно быть указано конкретное жилье
        if validation_applies and accommodation == "1" and location_selected and self.instance.check_apart and not apartment:
            raise ValidationError("При выборе проживания в квартире необходимо указать конкретную квартиру.")

        # Проверка доступности квартиры на период (исключая текущий процесс)
        if validation_applies and apartment and document and document.period_from and document.period_for:
            # Проверяем доступность (исключая текущий процесс)
            available_beds = apartment.get_available_beds(
                document.period_from,
                document.period_for,
                exclude_process=self.instance
            )

            if available_beds <= 0:
                # Квартира занята другими бронированиями
                busy_periods = apartment.get_busy_periods(
                    document.period_from,
                    document.period_for,
                    exclude_process=self.instance
                )

                msg = f"Квартира '{apartment}' недоступна на выбранный период (нет свободных мест)."
                if busy_periods:
                    msg += " Занята в периоды: "
                    for period in busy_periods:
                        msg += f"{period['start']} по {period['end']}; "
                    msg += "Выберите другую квартиру или измените даты."

                raise ValidationError(msg)

        return cleaned_data


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

        # Список полей для фильтрации
        person_fields = [
            "person_agreement", "person_executor", "person_clerk",
            "person_hr", "person_sd", "person_accounting"
        ]

        # Применяем фильтрацию для каждого поля
        for field_name in person_fields:
            if field_name in self.fields:
                # Фильтруем queryset, оставляя только активных пользователей
                self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                    is_active=True
                )
                # Добавляем multiple атрибут
                self.fields[field_name].widget.attrs.update({"multiple": "multiple"})

        # Применяем кастомные стили для всех полей
        for field in self.fields:
            make_custom_field(self.fields[field])
        # self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_clerk"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_sd"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_accounting"].widget.attrs.update({"multiple": "multiple", })
        # for field in self.fields:
        #     make_custom_field(self.fields[field])


class BusinessProcessRoutesUpdateForm(forms.ModelForm):
    class Meta:
        model = BusinessProcessRoutes
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Список полей для фильтрации
        person_fields = [
            "person_agreement", "person_executor", "person_clerk",
            "person_hr", "person_sd", "person_accounting"
        ]

        # Применяем фильтрацию для каждого поля
        for field_name in person_fields:
            if field_name in self.fields:
                # Фильтруем queryset, оставляя только активных пользователей
                self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                    is_active=True
                )
                # Добавляем multiple атрибут
                self.fields[field_name].widget.attrs.update({"multiple": "multiple"})

        # Применяем кастомные стили для всех полей
        for field in self.fields:
            make_custom_field(self.fields[field])
        # self.fields["person_agreement"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_executor"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_clerk"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_hr"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_sd"].widget.attrs.update({"multiple": "multiple", })
        # self.fields["person_accounting"].widget.attrs.update({"multiple": "multiple", })
        # for field in self.fields:
        #     make_custom_field(self.fields[field])


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
    """Форма добавления нового места производственной деятельности (МПД).

    Включает все реквизиты объекта, контактный email и пароль корпоративной почты,
    сумму дополнительной оплаты, авиационные метеорологические параметры (код ICAO, координаты)
    и системные переключатели интеграции (приказы бригад, планирование, контроль билетов, мониторинг погоды).
    """

    class Meta:
        model = PlaceProductionActivity
        fields = (
            "name",
            "short_name",
            "address",
            "icao_code",
            "latitude",
            "longitude",
            "elevation_msl_m",
            "elevation_source",
            "weather_source_preference",
            "email",
            "work_email_password",
            "additional_payment",
            "use_team_orders",
            "in_planning",
            "ticket_control",
            "weather_monitoring_enabled",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Введите полное наименование места деятельности",
                }
            ),
            "short_name": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Краткое наименование (МПД ...)",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Фактический адрес объекта",
                }
            ),
            "icao_code": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern text-uppercase font-monospace",
                    "placeholder": "UNNT",
                    "maxlength": "4",
                    "style": "letter-spacing: 2px;",
                }
            ),
            "latitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.000001",
                    "placeholder": "55.012345",
                }
            ),
            "longitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.000001",
                    "placeholder": "82.654321",
                }
            ),
            "elevation_msl_m": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.1",
                    "placeholder": "150.0",
                }
            ),
            "elevation_source": forms.Select(
                attrs={
                    "class": "form-select form-control-modern",
                }
            ),
            "weather_source_preference": forms.Select(
                attrs={
                    "class": "form-select form-control-modern",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "mpd_name@barkol.ru",
                }
            ),
            "work_email_password": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Пароль корпоративной почты",
                    "autocomplete": "new-password",
                }
            ),
            "additional_payment": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "use_team_orders": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "in_planning": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "ticket_control": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "weather_monitoring_enabled": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с применением единых стилей к полям."""
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class PlaceProductionActivityUpdateForm(forms.ModelForm):
    """Форма редактирования места производственной деятельности (МПД).

    Позволяет изменять все реквизиты объекта, контактные данные корпоративной почты,
    дополнительную оплату, метеорологические настройки (код ICAO, координаты, высотные отметки)
    и флаги использования объекта в бизнес-процессах.
    """

    class Meta:
        model = PlaceProductionActivity
        fields = (
            "name",
            "short_name",
            "address",
            "icao_code",
            "latitude",
            "longitude",
            "elevation_msl_m",
            "elevation_source",
            "weather_source_preference",
            "email",
            "work_email_password",
            "additional_payment",
            "use_team_orders",
            "in_planning",
            "ticket_control",
            "weather_monitoring_enabled",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Введите полное наименование места деятельности",
                }
            ),
            "short_name": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Краткое наименование (МПД ...)",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Фактический адрес объекта",
                }
            ),
            "icao_code": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern text-uppercase font-monospace",
                    "placeholder": "UNNT",
                    "maxlength": "4",
                    "style": "letter-spacing: 2px;",
                }
            ),
            "latitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.000001",
                    "placeholder": "55.012345",
                }
            ),
            "longitude": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.000001",
                    "placeholder": "82.654321",
                }
            ),
            "elevation_msl_m": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.1",
                    "placeholder": "150.0",
                }
            ),
            "elevation_source": forms.Select(
                attrs={
                    "class": "form-select form-control-modern",
                }
            ),
            "weather_source_preference": forms.Select(
                attrs={
                    "class": "form-select form-control-modern",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "mpd_name@barkol.ru",
                }
            ),
            "work_email_password": forms.TextInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "placeholder": "Пароль корпоративной почты",
                    "autocomplete": "new-password",
                }
            ),
            "additional_payment": forms.NumberInput(
                attrs={
                    "class": "form-control form-control-modern",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "use_team_orders": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "in_planning": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "ticket_control": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
            "weather_monitoring_enabled": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                    "role": "switch",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с применением единых стилей к полям."""
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
        widget=forms.Select(attrs={"class": "form-control form-control-modern", "data-plugin-selectTwo": True}),
        queryset=DataBaseUser.objects.filter(is_active=True).order_by('title', 'username'),
        label="Ответственный (Старший бригады)")

    time_sheets_place = forms.ModelChoiceField(
        widget=forms.Select(attrs={"class": "form-control form-control-modern", "data-plugin-selectTwo": True}),
        queryset=PlaceProductionActivity.objects.filter(use_team_orders=True),
        label="Место производства деятельности (МПД)")

    class Meta:
        model = TimeSheet
        fields = ['date', 'employee', 'time_sheets_place', 'notes', 'is_draft']

    def __init__(self, *args, **kwargs):
        """Инициализирует форму табеля с кастомными атрибутами."""
        super(TimeSheetForm, self).__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])


class ReportCardForm(forms.ModelForm):
    outfit_card = forms.ModelMultipleChoiceField(
        queryset=OutfitCard.objects.all(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "data-plugin-selectTwo": True, "multiple": True}),
        required=False,
        label="Карта-наряд"
    )
    employee = forms.ModelChoiceField(
        widget=forms.Select(attrs={"class": "form-control form-control-modern"}),
        queryset=DataBaseUser.objects.filter(is_active=True).order_by('title', 'username'),
        required=True,
        label="Сотрудник"
    )

    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control form-control-modern'}),
        label="Время начала"
    )

    end_time = forms.TimeField(
        required=False,
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


class MaintenanceEquipmentChoiceField(forms.ModelMultipleChoiceField):
    """Поле множественного выбора оборудования ТО с подробным метрологическим описанием.

    Отображает в выпадающем списке наименование оборудования, чертежный номер (P/N),
    заводской/серийный номер (S/N), код индивидуальной маркировки (п. 23 ФАП-145)
    и срок окончания действия текущей поверки или калибровки.
    """

    def label_from_instance(self, obj: MaintenanceEquipment) -> str:
        """Формирует информативную подпись для выпадающего списка выбора прибора.

        Args:
            obj (MaintenanceEquipment): Объект оборудования из реестра ТО.

        Returns:
            str: Строковое представление с P/N, S/N, маркировкой и сроком поверки.
        """
        parts = [obj.name]
        if obj.part_number:
            parts.append(f"P/N: {obj.part_number}")
        if obj.serial_number:
            parts.append(f"S/N: {obj.serial_number}")
        if obj.marking_code:
            parts.append(f"№ {obj.marking_code}")
        if obj.next_verification_date:
            parts.append(f"поверка до {obj.next_verification_date.strftime('%d.%m.%Y')}")
        else:
            parts.append("бессрочно / без поверки")
        return " | ".join(parts)


class OutfitCardForm(forms.ModelForm):
    """Форма создания и редактирования карты-наряда на ТО воздушного судна.

    Обеспечивает валидацию и ввод реквизитов наряда, наработки планера ВС (СНЭ, ППР,
    посадки), перенесенных дефектов (MEL/CDL/AMM), данных подтверждающего персонала,
    а также прикрепление контрольно-поверочной аппаратуры и специнструмента
    в соответствии с требованиями Федеральных авиационных правил (Приказ Минтранса РФ № 367,
    пп. 19–25 и 102-ФЗ).

    Args:
        *args: Позиционные аргументы ModelForm.
        **kwargs: Именованные аргументы, опционально содержащие 'user' (текущий пользователь).
    """

    outfit_card_place = forms.ModelChoiceField(
        queryset=PlaceProductionActivity.objects.filter(use_team_orders=True),
        label="МПД",
    )
    employee = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by("last_name"),
        label="Ответственный / Старший бригады",
    )
    certifying_staff = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by("last_name"),
        required=False,
        label="Специалист подтверждающего персонала (CRS)",
    )
    used_equipment = MaintenanceEquipmentChoiceField(
        queryset=MaintenanceEquipment.objects.filter(
            operational_status=EquipmentOperationalStatus.SERVICEABLE
        ).order_by("name"),
        required=False,
        label="Использованное оборудование, КПА и специнструмент (ФАП-145, пп. 19–25)",
        help_text="Выберите средства измерений, КПА и инструмент, фактически применявшиеся при ТО",
    )

    class Meta:
        model = OutfitCard
        fields = [
            "outfit_card_date",
            "start_time",
            "outfit_card_number",
            "employee",
            "outfit_card_place",
            "air_board",
            "operational_work",
            "periodic_work",
            "other_work",
            "notes",
            "scan_document",
            "outfit_card_date_end",
            "end_time",
            "flight_hours",
            "flight_hours_tsor",
            "flight_cycles",
            "deferred_defects",
            "deferred_defects_agreed",
            "test_flight_required",
            "certifying_staff",
            "crs_number",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Особые отметки, замечания..."}),
            "start_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "end_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "deferred_defects": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Перечень перенесенных дефектов по MEL/CDL/AMM..."}
            ),
            "deferred_defects_agreed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "test_flight_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "flight_hours": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "0.0"}),
            "flight_hours_tsor": forms.NumberInput(attrs={"step": "0.1", "min": "0", "placeholder": "0.0"}),
            "flight_cycles": forms.NumberInput(attrs={"min": "0", "placeholder": "0"}),
            "crs_number": forms.TextInput(attrs={"placeholder": "Номер свидетельства / CRS авторизации"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с ограничением прав бригады, загрузкой оборудования и стилизацией."""
        self.user = kwargs.pop("user", None)
        super(OutfitCardForm, self).__init__(*args, **kwargs)

        if self.user and not (getattr(self.user, "is_superuser", False) or getattr(self.user, "is_staff", False)):
            place = (
                CreatingTeam.objects.filter(senior_brigade=self.user)
                .exclude(cancellation=True)
                .values_list("date_start", "date_end", "place")
            )
            self.fields["employee"].queryset = DataBaseUser.objects.none()
            self.fields["outfit_card_place"].queryset = PlaceProductionActivity.objects.none()
            for item in place:
                if item[0] <= datetime.date.today() <= item[1]:
                    self.fields["employee"].queryset = DataBaseUser.objects.filter(pk=self.user.pk)
                    self.fields["outfit_card_place"].queryset = PlaceProductionActivity.objects.filter(pk=item[2])
        else:
            self.fields["employee"].queryset = DataBaseUser.objects.filter(is_active=True).order_by("last_name")
            self.fields["outfit_card_place"].queryset = PlaceProductionActivity.objects.filter(use_team_orders=True)

        if self.instance and self.instance.pk:
            current_eq = self.instance.used_equipment.all()
            self.fields["used_equipment"].initial = current_eq
            current_eq_ids = list(current_eq.values_list("pk", flat=True))
            self.fields["used_equipment"].queryset = MaintenanceEquipment.objects.filter(
                Q(operational_status=EquipmentOperationalStatus.SERVICEABLE)
                | Q(pk__in=current_eq_ids)
            ).order_by("name")

            if self.instance.is_signed:
                self.fields["used_equipment"].disabled = True

        for field in self.fields:
            make_custom_field(self.fields[field])

    def clean(self):
        """Комплексная валидация дат, отложенных дефектов, допуска персонала и оборудования (ФАП-145)."""
        cleaned_data = super(OutfitCardForm, self).clean()
        start_date = cleaned_data.get("outfit_card_date")
        end_date = cleaned_data.get("outfit_card_date_end")

        if start_date and end_date and start_date > end_date:
            raise ValidationError("Дата окончания должна быть больше чем дата начала")

        certifying_staff = cleaned_data.get("certifying_staff")
        air_board = cleaned_data.get("air_board")
        periodic_works = cleaned_data.get("periodic_work")
        target_date = end_date or start_date or datetime.date.today()
        aircraft_type = air_board.type_property if air_board else None
        require_base = bool(periodic_works and periodic_works.exists())

        if certifying_staff:
            from flight_planning.services import get_certifying_staff_authorization

            is_auth, doc_no, record = get_certifying_staff_authorization(
                employee=certifying_staff,
                aircraft_type=aircraft_type,
                target_date=target_date,
                require_base=require_base,
            )

            # Автоподстановка номера свидетельства / допуска CRS, если поле не заполнено вручную
            if doc_no and not cleaned_data.get("crs_number"):
                cleaned_data["crs_number"] = doc_no
            elif not cleaned_data.get("crs_number") and getattr(certifying_staff, "maintenance_staff_certificate", ""):
                cleaned_data["crs_number"] = certifying_staff.maintenance_staff_certificate

        # Проверка применимости выбранного оборудования к типу обслуживаемого ВС (п. 21 ФАП-145)
        selected_equipments = cleaned_data.get("used_equipment")
        if selected_equipments and aircraft_type:
            for eq in selected_equipments:
                if (
                    eq.applicable_aircraft_types.exists()
                    and not eq.applicable_aircraft_types.filter(pk=aircraft_type.pk).exists()
                ):
                    self.add_error(
                        "used_equipment",
                        f"Оборудование «{eq.name}» (P/N: {eq.part_number or '—'}) не применимо к типу ВС "
                        f"«{aircraft_type}» согласно реестру оборудования ТО (ФАП-145, п. 21)."
                    )

        return cleaned_data

    def save(self, commit=True):
        """Сохраняет карту-наряд и синхронизирует использованное оборудование ТО.

        Создает или актуализирует неизменяемые исторические снимки (OutfitCardEquipmentUsage)
        для каждого выбранного инструмента через attach_equipment_to_outfit_card.
        """
        instance = super().save(commit=commit)

        def save_equipment():
            if not instance.is_signed and "used_equipment" in self.cleaned_data:
                from hrdepartment_app.services.outfit_card_release_service import (
                    attach_equipment_to_outfit_card,
                    detach_equipment_from_outfit_card,
                )

                selected_equipments = list(self.cleaned_data.get("used_equipment") or [])
                selected_ids = {eq.pk for eq in selected_equipments}

                current_usages = {
                    usage.equipment_id: usage
                    for usage in instance.used_equipment_records.all()
                }
                current_ids = set(current_usages.keys())

                # Удаляем приборы, которые были исключены
                for eq_id in (current_ids - selected_ids):
                    usage_to_delete = current_usages[eq_id]
                    detach_equipment_from_outfit_card(instance, usage_to_delete.pk)

                # Добавляем или обновляем снимки для выбранных приборов
                for eq in selected_equipments:
                    if eq.pk not in current_ids:
                        attach_equipment_to_outfit_card(
                            outfit_card=instance,
                            equipment=eq,
                            user=self.user,
                        )

        if commit:
            save_equipment()
        else:
            old_save_m2m = getattr(self, "save_m2m", None)

            def new_save_m2m():
                if old_save_m2m:
                    old_save_m2m()
                save_equipment()

            self.save_m2m = new_save_m2m

        return instance


class MaintenanceReleaseCertificateCreateForm(forms.ModelForm):
    """Форма оформления и регистрации Свидетельства о ТО ВС (CRS) на портале.

    Позволяет выбрать карту-наряд (OutfitCard) и подтверждающий персонал (DataBaseUser),
    автоматически заполняя все параметры ВС, выполненные работы, наработку и даты.
    Свидетельству присваивается независимый сквозной номер в формате <seq>/<YY>.
    """

    outfit_card = forms.ModelChoiceField(
        queryset=OutfitCard.objects.all().order_by("-outfit_card_date", "-id"),
        required=True,
        label="Карта-наряд (основание)",
        empty_label="— Выберите карту-наряд —",
    )
    certifying_staff = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True).order_by("last_name"),
        required=True,
        label="Подтверждающий персонал",
        empty_label="— Выберите специалиста —",
    )
    maintenance_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата выполнения ТО ВС",
    )
    issue_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Дата свидетельства",
    )
    aircraft_type = forms.CharField(
        required=False,
        max_length=100,
        label="Тип ВС",
        widget=forms.TextInput(attrs={"placeholder": "Например: Ми-8Т, Ан-2"}),
    )
    tail_number = forms.CharField(
        required=False,
        max_length=50,
        label="Рег. № ВС (бортовой)",
        widget=forms.TextInput(attrs={"placeholder": "Например: RA-24022"}),
    )
    factory_number = forms.CharField(
        required=False,
        max_length=50,
        label="Зав. № ВС",
        widget=forms.TextInput(attrs={"placeholder": "Заводской номер планера"}),
    )
    operating_hours = forms.CharField(
        required=False,
        max_length=100,
        label="Наработка ВС",
        widget=forms.TextInput(attrs={"placeholder": "Например: 693 ч. 53 м."}),
    )
    maintenance_work_scope = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Перечень выполненных регламентов ТО, оперативных и дополнительных работ..."}),
        label="Вид ТО (выполненные работы)",
    )
    certifying_staff_license = forms.CharField(
        required=False,
        max_length=100,
        label="Свидетельство специалиста",
        widget=forms.TextInput(attrs={"placeholder": "Номер бессрочного свидетельства специалиста по ТО ВС"}),
    )
    signature_stamp = forms.CharField(
        required=False,
        max_length=255,
        label="Отметка о подписи / ПЭП",
        widget=forms.TextInput(attrs={"placeholder": "[Оформлено в СЭД БАРКОЛ]"}),
    )
    scan_file = forms.FileField(
        required=False,
        label="Скан свидетельства (при наличии)",
    )

    class Meta:
        model = MaintenanceReleaseCertificate
        fields = [
            "outfit_card",
            "certifying_staff",
            "maintenance_date",
            "issue_date",
            "aircraft_type",
            "tail_number",
            "factory_number",
            "operating_hours",
            "maintenance_work_scope",
            "certifying_staff_license",
            "signature_stamp",
            "scan_file",
        ]

    def __init__(self, *args, **kwargs):
        """Инициализирует форму, стилизуя контролы и настраивая понятные текстовые метки."""
        super().__init__(*args, **kwargs)
        for field in self.fields:
            make_custom_field(self.fields[field])
        self.fields["outfit_card"].label_from_instance = (
            lambda obj: f"Наряд № {obj.outfit_card_number} от {obj.outfit_card_date:%d.%m.%Y} (Борт: {obj.air_board})"
            if obj.outfit_card_date
            else f"Наряд № {obj.outfit_card_number} (Борт: {obj.air_board})"
        )
        self.fields["certifying_staff"].label_from_instance = (
            lambda u: f"{u.get_full_name()} [{u.maintenance_staff_certificate}]"
            if getattr(u, "maintenance_staff_certificate", "")
            else u.get_full_name()
        )
        if not self.initial.get("issue_date"):
            self.initial["issue_date"] = timezone.now().date()
        if not self.initial.get("signature_stamp"):
            self.initial["signature_stamp"] = "[Оформлено в СЭД БАРКОЛ]"

    def clean(self) -> Dict[str, Any]:
        """Комплексная валидация и автоматическое дозаполнение реквизитов из карты-наряда.

        Returns:
            Dict[str, Any]: Очищенные данные формы с автозаполненными параметрами.
        """
        cleaned_data = super().clean()
        card = cleaned_data.get("outfit_card")
        staff = cleaned_data.get("certifying_staff")

        if card:
            from hrdepartment_app.services.crs_document_service import (
                build_work_scope_text,
                format_hours_minutes,
            )
            if not cleaned_data.get("maintenance_date"):
                cleaned_data["maintenance_date"] = (
                    card.outfit_card_date_end or card.outfit_card_date or timezone.now().date()
                )
            if not cleaned_data.get("aircraft_type") and card.air_board and card.air_board.type_property:
                cleaned_data["aircraft_type"] = card.air_board.type_property.type_property
            if not cleaned_data.get("tail_number") and card.air_board:
                cleaned_data["tail_number"] = card.air_board.registration_number
            if not cleaned_data.get("factory_number") and card.air_board:
                cleaned_data["factory_number"] = card.air_board.factory_number or ""
            if not cleaned_data.get("operating_hours"):
                cleaned_data["operating_hours"] = format_hours_minutes(card.flight_hours)
            if not cleaned_data.get("maintenance_work_scope"):
                cleaned_data["maintenance_work_scope"] = build_work_scope_text(card)

        if staff:
            if not cleaned_data.get("certifying_staff_license") and getattr(staff, "maintenance_staff_certificate", ""):
                cleaned_data["certifying_staff_license"] = staff.maintenance_staff_certificate

        return cleaned_data


class MaintenanceEquipmentForm(forms.ModelForm):
    """Форма создания и редактирования единицы оборудования ТО ВС на портале (ФАП-145).

    Позволяет вносить и обновлять паспортные, эксплуатационные и метрологические данные
    оборудования, контрольно-поверочной аппаратуры и специального инструмента
    в соответствии с требованиями Федеральных авиационных правил (Приказ Минтранса РФ № 367)
    и Федерального закона от 26.06.2008 № 102-ФЗ.
    """

    class Meta:
        model = MaintenanceEquipment
        fields = [
            "type_model",
            "name",
            "equipment_type",
            "part_number",
            "serial_number",
            "inventory_number",
            "marking_code",
            "applicable_aircraft_types",
            "operational_status",
            "verification_type",
            "last_verification_date",
            "next_verification_date",
            "interval_value",
            "interval_unit",
            "interval_source",
            "arshin_verification_number",
            "verification_organization",
            "certificate_scan",
            "location",
            "production_place",
            "responsible_person",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Особые примечания, условия хранения или поверки..."}),
            "interval_source": forms.TextInput(attrs={"placeholder": "РЭ изготовителя, методика поверки, регламент организации..."}),
            "arshin_verification_number": forms.TextInput(attrs={"placeholder": "Номер свидетельства или записи в реестре ФГИС «АРШИН»"}),
            "marking_code": forms.TextInput(attrs={"placeholder": "Индивидуальный номер маркировки/бирки (п. 23 ФАП-145)"}),
            "part_number": forms.TextInput(attrs={"placeholder": "P/N чертежный номер изделия"}),
            "serial_number": forms.TextInput(attrs={"placeholder": "S/N заводской номер"}),
            "inventory_number": forms.TextInput(attrs={"placeholder": "Бухгалтерский инвентарный номер"}),
            "location": forms.TextInput(attrs={"placeholder": "Инструментальная кладовая, участок, контейнер..."}),
            "verification_organization": forms.TextInput(attrs={"placeholder": "Наименование организации-поверителя / ЦСМ"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы со стилизацией полей виджетов через make_custom_field."""
        super().__init__(*args, **kwargs)
        if "type_model" in self.fields:
            self.fields["type_model"].queryset = EquipmentTypeModel.objects.select_related("equipment_name").order_by(
                "equipment_name__name", "name"
            )
            self.fields["type_model"].empty_label = "--- Выберите утвержденный тип/модель СИ ---"
        for field_name, field in self.fields.items():
            make_custom_field(field)


class EquipmentTransferRequestForm(forms.ModelForm):
    """Форма создания и редактирования заявки на меж-МПД перемещение оборудования (ФАП-145)."""

    class Meta:
        model = EquipmentTransferRequest
        fields = [
            "equipment",
            "from_mpd",
            "to_mpd",
            "target_periodic_work",
            "target_operational_work",
            "required_date",
            "status",
            "tracking_number",
            "notes",
        ]
        widgets = {
            "required_date": forms.DateInput(attrs={"type": "date"}),
            "tracking_number": forms.TextInput(attrs={"placeholder": "Номер экспресс-накладной, рейс или сопроводительный документ"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Служебные примечания для службы логистики..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            make_custom_field(field)


class EquipmentAllocationFilterForm(forms.Form):
    """Форма параметров подбора оборудования ТО на интерактивном дашборде."""

    WORK_TYPE_CHOICES = (
        ("periodic", "Периодическое ТО (ПТО)"),
        ("operational", "Оперативное обслуживание (ОТО)"),
    )

    work_type = forms.ChoiceField(
        label="Категория обслуживания",
        choices=WORK_TYPE_CHOICES,
        initial="periodic",
    )
    periodic_work = forms.ModelChoiceField(
        label="Форма ПТО",
        queryset=PeriodicWork.objects.all().select_related("air_bord_type").order_by("air_bord_type__type_property", "name"),
        required=False,
        empty_label="--- Выберите регламентную форму ПТО ---",
    )
    operational_work = forms.ModelChoiceField(
        label="Форма ОТО",
        queryset=OperationalWork.objects.all().select_related("air_bord_type").order_by("air_bord_type__type_property", "name"),
        required=False,
        empty_label="--- Выберите оперативное обслуживание ОТО ---",
    )
    target_mpd = forms.ModelChoiceField(
        label="Целевое МПД проведения ТО",
        queryset=PlaceProductionActivity.objects.all().order_by("name"),
        empty_label="--- Выберите МПД проведения ТО ---",
    )
    date_start = forms.DateField(
        label="Дата начала ТО",
        initial=timezone.now().date,
        input_formats=["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"],
        help_text="Дата планируемого начала проведения работ",
    )
    safety_buffer_days = forms.IntegerField(
        label="Буфер надежности (дней)",
        initial=7,
        min_value=1,
        max_value=90,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            make_custom_field(field)

    def clean(self):
        cleaned_data = super().clean()
        work_type = cleaned_data.get("work_type")
        periodic_work = cleaned_data.get("periodic_work")
        operational_work = cleaned_data.get("operational_work")

        if work_type == "periodic" and not periodic_work:
            self.add_error("periodic_work", "Для периодического ТО выберите регламентную форму (ПТО).")
        elif work_type == "operational" and not operational_work:
            self.add_error("operational_work", "Для оперативного ТО выберите форму обслуживания (ОТО).")

        return cleaned_data


class MaintenanceWorkEquipmentRequirementForm(forms.ModelForm):
    """Форма добавления и редактирования требования табеля оснащения ТО к оборудованию (ФАП-145).

    Позволяет инженеру ПТО закрепить за конкретной формой периодического или оперативного ТО
    обязательное наименование оборудования (EquipmentName), строгий тип/модель СИ (EquipmentTypeModel),
    список взаимозаменяемых типов-аналогов (allowed_substitutes), требуемое количество и критичность.
    """

    class Meta:
        model = MaintenanceWorkEquipmentRequirement
        fields = [
            "equipment_name",
            "required_type",
            "allowed_substitutes",
            "quantity",
            "is_mandatory",
            "task_reference",
        ]
        widgets = {
            "task_reference": forms.TextInput(attrs={"placeholder": "Пункт РО или техкарты (напр. 'РО п. 4.2.1')"}),
            "is_mandatory": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы с ограничением выбора моделей по наименованию."""
        self.periodic_work = kwargs.pop("periodic_work", None)
        self.operational_work = kwargs.pop("operational_work", None)
        super().__init__(*args, **kwargs)
        if self.periodic_work and not self.instance.periodic_work_id:
            self.instance.periodic_work = self.periodic_work
        if self.operational_work and not self.instance.operational_work_id:
            self.instance.operational_work = self.operational_work
        self.fields["equipment_name"].empty_label = "--- Выберите наименование инструмента/СИ ---"
        self.fields["equipment_name"].queryset = EquipmentName.objects.all().order_by("name")

        self.fields["required_type"].empty_label = "--- Любой исправный тип данного наименования ---"
        self.fields["required_type"].queryset = EquipmentTypeModel.objects.select_related("equipment_name").order_by("equipment_name__name", "name")

        self.fields["allowed_substitutes"].queryset = EquipmentTypeModel.objects.select_related("equipment_name").order_by("equipment_name__name", "name")

        eq_name_id = None
        if self.is_bound:
            eq_name_id = self.data.get("equipment_name")
        elif self.instance and self.instance.pk and self.instance.equipment_name_id:
            eq_name_id = self.instance.equipment_name_id

        if eq_name_id:
            try:
                self.fields["required_type"].queryset = EquipmentTypeModel.objects.filter(equipment_name_id=eq_name_id).order_by("name")
                self.fields["allowed_substitutes"].queryset = EquipmentTypeModel.objects.filter(equipment_name_id=eq_name_id).order_by("name")
            except (ValueError, TypeError):
                pass

        for field_name, field in self.fields.items():
            if field_name != "is_mandatory":
                make_custom_field(field)

    def clean(self):
        cleaned_data = super().clean()
        equipment_name = cleaned_data.get("equipment_name")
        required_type = cleaned_data.get("required_type")

        if equipment_name and required_type:
            if required_type.equipment_name_id != equipment_name.pk:
                self.add_error(
                    "required_type",
                    f"Тип «{required_type.name}» не относится к наименованию «{equipment_name.name}»."
                )

        return cleaned_data



class EquipmentVerificationRecordForm(forms.ModelForm):
    """Форма регистрации свидетельства о поверке/калибровке оборудования на портале (102-ФЗ).

    Позволяет внести результаты метрологического контроля, данные аккредитованного поверителя,
    номер записи во ФГИС «АРШИН» и прикрепить электронный скан документа.
    При сохранении автоматически обновляет даты очередной поверки и выводит прибор из изолятора брака.
    """

    class Meta:
        model = EquipmentVerificationRecord
        fields = [
            "equipment",
            "verification_type",
            "verification_date",
            "valid_until",
            "arshin_number",
            "organization",
            "result_serviceable",
            "certificate_scan",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Результаты измерений, протокол поверки..."}),
            "arshin_number": forms.TextInput(attrs={"placeholder": "Регистрационный номер во ФГИС «АРШИН»"}),
            "organization": forms.TextInput(attrs={"placeholder": "ФБУ ЦСМ или аккредитованная метрологическая служба"}),
            "result_serviceable": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы со стилизацией полей виджетов через make_custom_field."""
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            make_custom_field(field)


class EquipmentExcelImportForm(forms.Form):
    """Форма пакетного импорта оборудования и средств измерений из Excel (.xlsx / .xlsm).

    Обеспечивает загрузку книги Excel с метрологическим графиком, выбор листа,
    режима тестового прогона (Dry-Run) и первичную валидацию файла.

    Attributes:
        excel_file: Загружаемый файл книги Excel (.xlsx, .xlsm).
        sheet_name: Имя рабочего листа для импорта.
        dry_run: Режим симуляции без фиксации изменений в базе данных.
    """

    excel_file = forms.FileField(
        label="Файл Excel с метрологическим графиком (.xlsx / .xlsm)",
        help_text="Поддерживаются книги Excel (.xlsx, .xlsm), содержащие столбцы реестра СИ и инструмента",
        widget=forms.FileInput(attrs={"accept": ".xlsx,.xlsm"}),
    )
    sheet_name = forms.CharField(
        label="Имя рабочего листа",
        max_length=150,
        initial="Все СИ и Инструмент",
        help_text="Наименование вкладки Excel, из которой выполняется загрузка",
    )
    dry_run = forms.BooleanField(
        label="Тестовый прогон (Dry-Run)",
        required=False,
        initial=True,
        help_text="Если флаг установлен, выполняется проверка файла и вывод отчета без записи в базу данных",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
    )

    def __init__(self, *args, **kwargs):
        """Инициализация формы с применением единой стилизации make_custom_field."""
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != "dry_run":
                make_custom_field(field)

    def clean_excel_file(self):
        """Валидация формата загружаемого файла по расширению."""
        uploaded = self.cleaned_data.get("excel_file")
        if uploaded:
            ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
            if ext not in ("xlsx", "xlsm"):
                raise ValidationError("Разрешены только файлы электронных таблиц Microsoft Excel (.xlsx, .xlsm).")
        return uploaded


class DataBaseUserEventAddForm(forms.ModelForm):
    place = forms.ModelChoiceField(queryset=PlaceProductionActivity.objects.filter(use_team_orders=True))
    place.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = DataBaseUserEvent
        fields = (
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
        self.user_id = kwargs.pop("user")  # Сохраняем ID пользователя
        super(DataBaseUserEventAddForm, self).__init__(*args, **kwargs)

        # Получаем объект пользователя
        self.user = DataBaseUser.objects.get(pk=self.user_id)

        self.fields["checked"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["road"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.person = self.user
        if commit:
            instance.save()
        return instance


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


class LaborProtectionInstructionsAddForm(forms.ModelForm):
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = LaborProtectionInstructions
        fields = (
            "executor",
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "allowed_placed",
            "validity_period_start",
            "validity_period_end",
            "actuality",
            "parent_document",
            "document_name",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(LaborProtectionInstructionsAddForm, self).__init__(*args, **kwargs)
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
        for field in self.fields:
            make_custom_field(self.fields[field])


class LaborProtectionInstructionsUpdateForm(forms.ModelForm):
    access = forms.ModelChoiceField(queryset=AccessLevel.objects.all())
    access.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )
    storage_location_division = forms.ModelChoiceField(queryset=Division.objects.all())
    storage_location_division.widget.attrs.update(
        {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
    )

    class Meta:
        model = LaborProtectionInstructions
        fields = (
            "document_date",
            "document_number",
            "doc_file",
            "scan_file",
            "access",
            "storage_location_division",
            "validity_period_start",
            "validity_period_end",
            "parent_document",
            "allowed_placed",
            "actuality",
            "document_name",
        )

    def __init__(self, *args, **kwargs):
        """
        :param args:
        :param kwargs: Содержит словарь, в котором содержится текущий пользователь
        """
        self.user = kwargs.pop("user")
        super(LaborProtectionInstructionsUpdateForm, self).__init__(*args, **kwargs)
        self.fields["allowed_placed"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        self.fields["actuality"].widget.attrs.update(
            {"class": "todo-check", "data-plugin-ios-switch": True}
        )
        for field in self.fields:
            make_custom_field(self.fields[field])


class StudentAgreementForm(forms.ModelForm):
    class Meta:
        model = StudentAgreement
        fields = "__all__"
        widgets = {
            'training_unit': forms.SelectMultiple(attrs={
                'id': 'id_training_unit',
                'multiple': 'multiple',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Определяем, какой УЦ выбран (из POST-данных или из экземпляра)
        center_id = None
        if self.data and self.data.get('training_center_name'):
            center_id = self.data.get('training_center_name')
        elif self.instance.pk and self.instance.training_center_name_id:
            center_id = self.instance.training_center_name_id

        # Определяем выбранный договор
        contract_id = None
        if self.data and self.data.get('counteragent_contract'):
            contract_id = self.data.get('counteragent_contract')
        elif self.instance.pk and self.instance.counteragent_contract_id:
            contract_id = self.instance.counteragent_contract_id

        # Формируем queryset для договоров
        if center_id:
            queryset = Contract.objects.filter(
                contract_counteragent_id=center_id,
                type_of_contract__type_contract__icontains='Обучение'  # Тот же фильтр, что в AJAX
            )
            # Добавляем текущий выбранный договор, чтобы валидация прошла
            if contract_id:
                queryset = queryset | Contract.objects.filter(pk=contract_id)
            self.fields['counteragent_contract'].queryset = queryset
        else:
            self.fields['counteragent_contract'].queryset = Contract.objects.none()

        # Определяем, какая программа выбрана (из POST-данных или из экземпляра)
        program_id = None
        if self.data and self.data.get('training_program'):
            program_id = self.data.get('training_program')
        elif self.instance.pk and self.instance.training_program_id:
            program_id = self.instance.training_program_id

        # Формируем queryset для программ
        if center_id:
            queryset = TrainingProgram.objects.filter(counteragent_name_id=center_id)
            # Важно: добавляем выбранную программу в queryset, даже если она не входит в фильтр
            # (например, только что созданная через модальное окно)
            if program_id:
                queryset = queryset | TrainingProgram.objects.filter(pk=program_id)
            self.fields['training_program'].queryset = queryset
        else:
            self.fields['training_program'].queryset = TrainingProgram.objects.none()

        # Формируем queryset для модулей (ИСПРАВЛЕНО)
        if program_id:
            # Базовый фильтр: модули текущей программы
            queryset = TrainingUnit.objects.filter(program_units_id=program_id)

            # Собираем выбранные модули из POST-данных или экземпляра
            selected_pks = []
            if self.data and self.data.getlist('training_unit'):
                selected_pks = self.data.getlist('training_unit')
            elif self.instance.pk:
                selected_pks = self.instance.training_unit.values_list('pk', flat=True)

            # Добавляем выбранные модули в queryset, даже если их нет в базовом фильтре
            if selected_pks:
                queryset = queryset | TrainingUnit.objects.filter(pk__in=selected_pks)

            self.fields['training_unit'].queryset = queryset.distinct()
        else:
            self.fields['training_unit'].queryset = TrainingUnit.objects.none()
        self.fields['training_unit'].required = False
        self.fields["full_name"].queryset = DataBaseUser.objects.filter(is_active=True)
        for field in self.fields:
            make_custom_field(self.fields[field])


class TrainingDebtReportForm(forms.Form):
    employee = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True),
        label='Сотрудник',
        widget=forms.Select(attrs={
            'class': 'form-control form-control-modern',
            'data-plugin-selectTwo': True
        })
    )
    dismissal_date = forms.DateField(
        label='Дата увольнения',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control form-control-modern',
            'data-date-language': 'ru',
            'todayBtn': True,
            'clearBtn': True,
            'data-plugin-options': '{"orientation": "bottom"}',
            'value': datetime.datetime.now().date().isoformat()
        }),
        initial=datetime.datetime.now().date()
    )


class TrainingProgramQuickForm(forms.ModelForm):
    """Мини-форма для быстрого создания программы в модальном окне"""

    class Meta:
        model = TrainingProgram
        fields = ['program_name', 'counteragent_name']
        widgets = {
            'counteragent_name': forms.HiddenInput(),  # Скрытое поле
            'program_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите название программы',
                'autofocus': True
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['program_name'].required = True


class TrainingUnitQuickForm(forms.ModelForm):
    """Мини-форма для быстрого создания модуля в модальном окне"""

    class Meta:
        model = TrainingUnit
        fields = ['unit_name', 'program_units']
        widgets = {
            'program_units': forms.HiddenInput(),  # Скрытое поле
            'unit_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите название модуля',
                'autofocus': True
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_name'].required = True


class PowerOfAttorneyForm(forms.ModelForm):
    """
    Форма для создания и редактирования доверенностей.
    """
    initiator_name_user = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True),
        label='ФИО инициатора',
    )

    grantee_name_user = forms.ModelChoiceField(
        queryset=DataBaseUser.objects.filter(is_active=True),
        label='ФИО поверенного',
    )

    class Meta:
        model = PowerOfAttorney
        fields = (
            'number', 'issue_date', 'expiry_date',
            'initiator_name_user', 'grantee_name_user',
            'organization', 'cancellation_date', 'scan_file'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Получаем всех пользователей, которые есть в person_clerk для типа процесса "3" (Доверенности)
        # Предполагается, что существует только один активный маршрут для доверенностей
        # Если может быть несколько, используйте values_list('person_clerk__id', flat=True) и distinct()
        business_route = BusinessProcessRoutes.objects.filter(
            business_process_type="3"
        ).first()  # Или используйте .last() или другой метод получения нужного маршрута

        if business_route:
            # Фильтруем queryset для initiator_name_user
            filtered_users = business_route.person_clerk.filter(is_active=True)
            self.fields['initiator_name_user'].queryset = filtered_users
        else:
            # Если маршрут не найден, можно вернуть пустой queryset или оставить всех
            self.fields['initiator_name_user'].queryset = DataBaseUser.objects.none()

        # Применяем кастомную стилизацию ко всем полям
        for field in self.fields:
            make_custom_field(self.fields[field])


class PeriodicWorkForm(forms.ModelForm):
    """Форма создания и редактирования периодических регламентных работ.

    Attributes:
        Meta: Мета-класс с привязкой к модели PeriodicWork и списком полей.
    """

    class Meta:
        model = PeriodicWork
        fields = (
            "air_bord_type",
            "code",
            "name",
            "ratio",
            "lag_minus",
            "lag_plus",
            "color",
            "description",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Наименование регламента (например, МИ-8Т - Ф-1)"}),
            "code": forms.TextInput(attrs={"placeholder": "Код регламента (например, Ф-1, 100 часов)"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Подробное описание регламентных процедур"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализирует форму и настраивает стилизацию виджетов Porto Admin."""
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            make_custom_field(self.fields[field_name])
        if "air_bord_type" in self.fields:
            self.fields["air_bord_type"].widget.attrs.update(
                {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
            )
        if "color" in self.fields:
            self.fields["color"].widget.attrs.update(
                {"class": "form-control form-control-modern"}
            )


class OperationalWorkForm(forms.ModelForm):
    """Форма создания и редактирования видов оперативных работ.

    Attributes:
        Meta: Мета-класс с привязкой к модели OperationalWork и списком полей.
    """

    class Meta:
        model = OperationalWork
        fields = (
            "air_bord_type",
            "code",
            "name",
            "description",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Наименование оперативной работы"}),
            "code": forms.TextInput(attrs={"placeholder": "Код работы (например, А1, А2)"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Описание оперативных процедур"}),
        }

    def __init__(self, *args, **kwargs):
        """Инициализирует форму и настраивает стилизацию виджетов Porto Admin."""
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            make_custom_field(self.fields[field_name])
        if "air_bord_type" in self.fields:
            self.fields["air_bord_type"].widget.attrs.update(
                {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
            )


class AircraftHoursTrackingForm(forms.ModelForm):
    """Форма ручной фиксации наработки воздушного судна (ФАП-367).

    Обеспечивает ввод показателей налета планера СНЭ, ППР и количества посадок
    с привязкой к конкретному борту ВС и дате фиксации.
    """

    air_board = forms.ModelChoiceField(
        queryset=Estate.objects.filter(decommission_date__isnull=True, type_property__isnull=False)
        .select_related("type_property")
        .order_by("type_property__type_property", "registration_number"),
        label="Воздушное судно",
        empty_label="— Выберите воздушное судно —",
    )

    class Meta:
        model = AircraftHoursTracking
        fields = (
            "air_board",
            "record_date",
            "flight_hours",
            "flight_hours_tsor",
            "flight_cycles",
            "notes",
        )
        widgets = {
            "record_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control form-control-modern",
                }
            ),
            "flight_hours": forms.NumberInput(
                attrs={
                    "step": "0.1",
                    "min": "0",
                    "placeholder": "0.0",
                    "class": "form-control form-control-modern",
                }
            ),
            "flight_hours_tsor": forms.NumberInput(
                attrs={
                    "step": "0.1",
                    "min": "0",
                    "placeholder": "0.0",
                    "class": "form-control form-control-modern",
                }
            ),
            "flight_cycles": forms.NumberInput(
                attrs={
                    "min": "0",
                    "placeholder": "0",
                    "class": "form-control form-control-modern",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Основание, источник данных или примечание...",
                    "class": "form-control form-control-modern",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        """Инициализация формы со стилизацией полей."""
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            make_custom_field(self.fields[field_name])
        if "air_board" in self.fields:
            self.fields["air_board"].widget.attrs.update(
                {"class": "form-control form-control-modern", "data-plugin-selectTwo": True}
            )
        if not self.initial.get("record_date") and not self.instance.pk:
            self.initial["record_date"] = datetime.date.today()

    def clean_record_date(self):
        """Валидация даты фиксации: запрет ввода дат из далекого будущего."""
        rec_date = self.cleaned_data.get("record_date")
        if rec_date and rec_date > datetime.date.today() + datetime.timedelta(days=1):
            raise ValidationError("Дата фиксации наработки не может быть в будущем.")
        return rec_date


class AircraftHoursImportForm(forms.Form):
    """Форма пакетной загрузки наработки ВС из файла Excel или CSV."""

    file = forms.FileField(
        label="Файл с данными наработки",
        help_text="Поддерживаются файлы Excel (.xlsx) и CSV (.csv). Скачайте эталонный шаблон для заполнения.",
        validators=[FileExtensionValidator(allowed_extensions=["xlsx", "csv"])],
        widget=forms.FileInput(
            attrs={
                "class": "form-control form-control-modern",
                "accept": ".xlsx,.csv",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Инициализация формы с применением стилей."""
        super().__init__(*args, **kwargs)
        make_custom_field(self.fields["file"])

