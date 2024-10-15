import datetime
from calendar import monthrange

from dateutil import rrule
from dateutil.relativedelta import relativedelta
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django import forms
from django.forms import inlineformset_factory
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DetailView,
    DeleteView, View,
)
from loguru import logger

from administration_app.models import PortalProperty, Notification
from administration_app.utils import (
    change_session_context,
    change_session_queryset,
    change_session_get,
    format_name_initials,
    get_jsons_data,
    ending_day,
    get_history,
    get_year_interval, ajax_search, send_notification,
)
from customers_app.models import DataBaseUser, Counteragent
from djangoProject.settings import EMAIL_HOST_USER
from hrdepartment_app.forms import (
    MedicalExaminationAddForm,
    MedicalExaminationUpdateForm,
    OfficialMemoUpdateForm,
    OfficialMemoAddForm,
    ApprovalOficialMemoProcessAddForm,
    ApprovalOficialMemoProcessUpdateForm,
    BusinessProcessDirectionAddForm,
    BusinessProcessDirectionUpdateForm,
    MedicalOrganisationAddForm,
    MedicalOrganisationUpdateForm,
    PurposeAddForm,
    PurposeUpdateForm,
    DocumentsOrderUpdateForm,
    DocumentsOrderAddForm,
    DocumentsJobDescriptionUpdateForm,
    DocumentsJobDescriptionAddForm,
    PlaceProductionActivityAddForm,
    PlaceProductionActivityUpdateForm,
    ApprovalOficialMemoProcessChangeForm,
    ReportCardAddForm,
    ReportCardUpdateForm,
    ProvisionsUpdateForm,
    ProvisionsAddForm,
    OficialMemoCancelForm, GuidanceDocumentsUpdateForm, GuidanceDocumentsAddForm, CreatingTeamAddForm,
    CreatingTeamUpdateForm, CreatingTeamAgreedForm, CreatingTeamSetNumberForm, TimeSheetForm,
    ReportCardForm, OutfitCardForm,
)
from hrdepartment_app.hrdepartment_util import (
    get_medical_documents,
    send_mail_change,
    get_month,
    get_working_hours, get_notify,
)
from hrdepartment_app.models import (
    Medical,
    OfficialMemo,
    ApprovalOficialMemoProcess,
    BusinessProcessDirection,
    MedicalOrganisation,
    Purpose,
    DocumentsJobDescription,
    DocumentsOrder,
    PlaceProductionActivity,
    ReportCard,
    ProductionCalendar,
    Provisions, GuidanceDocuments, CreatingTeam, TimeSheet, OutfitCard,
)
from hrdepartment_app.tasks import send_mail_notification, get_year_report


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


# Create your views here.
class MedicalOrganisationList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = MedicalOrganisation
    permission_required = "customers_app.view_medicalorganisation"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            medicals = MedicalOrganisation.objects.all()
            data = [medical.get_data() for medical in medicals]
            response = {"data": data}
            return JsonResponse(response)
        count = 0
        if self.request.GET.get("update") == "0":
            todos = get_jsons_data("Catalog", "МедицинскиеОрганизации", 0)
            # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
            for item in todos["value"]:
                if not item["DeletionMark"]:
                    divisions_kwargs = {
                        "ref_key": item["Ref_Key"],
                        "description": item["Description"],
                        "ogrn": item["ОГРН"],
                        "address": item["Адрес"],
                    }
                    MedicalOrganisation.objects.update_or_create(
                        ref_key=item["Ref_Key"], defaults=divisions_kwargs
                    )
            url_match = reverse_lazy("hrdepartment_app:medicalorg_list")
            return redirect(url_match)
        change_session_get(self.request, self)
        return super(MedicalOrganisationList, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        """
        Извлекает контекстные данные для представления.

        Параметры:
            object_list (список): список объектов, которые будут отображаться в представлении. По умолчанию — Нет.
            **kwargs (dict): дополнительные аргументы ключевого слова.

        Возврат:
            dict: данные контекста для представления.
        """
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Медицинские организации"
        return context

    def get_queryset(self):
        """
        Retrieves all MedicalOrganisation objects.

        :param self: The instance of the class.
        :return: A QuerySet containing all MedicalOrganisation objects.
        """
        return MedicalOrganisation.objects.all()


class MedicalOrganisationAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationAddForm
    permission_required = "customers_app.add_medicalorganisation"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить медицинскую организацию"
        return context


class MedicalOrganisationUpdate(
    PermissionRequiredMixin, LoginRequiredMixin, UpdateView
):
    model = MedicalOrganisation
    form_class = MedicalOrganisationUpdateForm
    permission_required = "customers_app.change_medicalorganisation"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context


class MedicalExamination(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = Medical
    permission_required = "hrdepartment_app.view_medical"

    # paginate_by = 10
    # item_sorted = 'date_entry'
    # sorted_list = ['number', 'date_entry', 'person', 'person__user_work_profile__job__name', 'organisation',
    #                'type_inspection']

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Медицинские направления"
        change_session_context(context, self)
        return context

    def get(self, request, *args, **kwargs):
        if self.request.GET.get("update") == "0":
            error = get_medical_documents()
            if error:
                return render(
                    request,
                    "hrdepartment_app/medical_list.html",
                    {"error": f"{error}: Необходимо обновить список организаций."},
                )
            url_match = reverse_lazy("hrdepartment_app:medical_list")
            return redirect(url_match)

        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['number', 'date_entry',
                           'person__title', 'organisation__description', 'working_status',
                           'view_inspection', 'type_inspection',
                           ]
            context = ajax_search(request, self, search_list, Medical, query)
            return JsonResponse(context, safe=False)

        return super(MedicalExamination, self).get(request, *args, **kwargs)


class MedicalExaminationAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = Medical
    form_class = MedicalExaminationAddForm
    permission_required = "hrdepartment_app.add_medical"

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationAdd, self).get_context_data(**kwargs)
        content["all_person"] = DataBaseUser.objects.filter(type_users="staff_member")
        content["all_contragent"] = Counteragent.objects.all()
        content["all_status"] = Medical.type_of
        content["all_harmful"] = ""
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить медицинское направление"
        return content

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:medical_list")
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class MedicalExaminationUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Medical
    form_class = MedicalExaminationUpdateForm
    template_name = "hrdepartment_app/medical_form_update.html"
    permission_required = "hrdepartment_app.change_medical"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:medical_list")


class OfficialMemoList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = OfficialMemo
    permission_required = "hrdepartment_app.view_officialmemo"

    def get(self, request, *args, **kwargs):

        query = Q()
        if not request.user.is_superuser or not request.user.is_staff:
            if request.user.user_work_profile.job.division_affiliation.pk != 1:
                query &= Q(responsible__user_work_profile__job__division_affiliation__pk=
                           request.user.user_work_profile.job.division_affiliation.pk)
            if not request.user.user_work_profile.job.right_to_approval:
                query &= Q(person__pk=request.user.pk)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['type_trip', 'person__title',
                           'person__user_work_profile__job__name', 'place_production_activity__name',
                           'purpose_trip__title',
                           'period_from', 'period_for', 'accommodation',
                           'order__document_number', 'comments', 'period_from',
                           ]
            context = ajax_search(request, self, search_list, OfficialMemo, query)
            return JsonResponse(context, safe=False)
        return super(OfficialMemoList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(OfficialMemoList, self).get_queryset().order_by("pk")
        if not self.request.user.is_superuser:
            user_division = DataBaseUser.objects.get(
                pk=self.request.user.pk
            ).user_work_profile.divisions
            qs = (
                OfficialMemo.objects.filter(
                    responsible__user_work_profile__divisions=user_division
                )
                .order_by("period_from")
                .reverse()
            )
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(OfficialMemoList, self).get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Служебные записки"
        return context


class OfficialMemoAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = OfficialMemo
    form_class = OfficialMemoAddForm
    permission_required = "hrdepartment_app.add_officialmemo"

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoAdd, self).get_context_data(**kwargs)
        # content['all_status'] = OfficialMemo.type_of_accommodation
        # Генерируем список сотрудников, которые на текущий момент времени не находятся в СП
        users_list = [
            person.person_id
            for person in OfficialMemo.objects.filter(
                Q(period_from__lte=datetime.datetime.today())
                & Q(period_for__gte=datetime.datetime.today())
            )
        ]
        # Выбираем из базы тех сотрудников, которые содержатся в списке users_list и исключаем из него суперпользователя
        # content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(pk__in=users_list).exclude(is_superuser=True)
        user_job = self.request.user
        if self.request.user.user_work_profile.divisions.type_of_role == '2':
            content["form"].fields["person"].queryset = (
                DataBaseUser.objects.filter(is_active=True).exclude(username="proxmox")
            )
        else:
            content["form"].fields["person"].queryset = (
                DataBaseUser.objects.filter(
                    user_work_profile__job__division_affiliation__pk=user_job.user_work_profile.job.division_affiliation.pk
                )
                .exclude(username="proxmox")
                .exclude(is_active=False)
            )
        content["form"].fields[
            "place_production_activity"
        ].queryset = PlaceProductionActivity.objects.all()
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить служебную записку"
        return content

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:memo_list")

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get("employee", None)
        period_from = request.GET.get("period_from", None)
        memo_type = request.GET.get("memo_type", None)
        try:
            person = DataBaseUser.objects.get(pk=employee)
            division = str(person.user_work_profile.divisions)
        except DataBaseUser.DoesNotExist:
            pass
        if memo_type and employee:
            html = {"employee": "", "memo_type": ""}
            if memo_type == "2":
                memo_list = OfficialMemo.objects.filter(
                    Q(person=employee)
                    & Q(official_memo_type="1")
                    & Q(docs__accepted_accounting=False)
                ).exclude(cancellation=True)
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                html["memo_type"] = memo_obj_list
                html["employee"] = division
                return JsonResponse(html)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, "%Y-%m-%d")
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date)
            ).exclude(cancellation=True)
            try:
                filter_string = datetime.datetime.strptime(
                    "1900-01-01", "%Y-%m-%d"
                ).date()
                for item in filters:
                    if item.period_for > filter_string:
                        filter_string = item.period_for
            except AttributeError:
                logger.info(
                    f"За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}"
                )
            if filters.count() > 0:
                # html = filter_string + datetime.timedelta(days=1)
                label = "Внимание, в заданный интервал имеются другие СЗ:"
                for item in filters:
                    label += " " + str(item) + ";"
                html = label
                return JsonResponse(html, safe=False)
        # Согласно приказу, ограничиваем последним днем предыдущего и первым днем следующего месяцев
        interval = request.GET.get("interval", None)
        if interval:
            request_day = datetime.datetime.strptime(interval, "%Y-%m-%d").day
            request_month = datetime.datetime.strptime(interval, "%Y-%m-%d").month
            request_year = datetime.datetime.strptime(interval, "%Y-%m-%d").year
            current_days = monthrange(request_year, request_month)[1]
            if request_month < 12:
                next_days = monthrange(request_year, request_month + 1)[1]
                next_month = request_month + 1
                next_year = request_year
            else:
                next_days = monthrange(request_year + 1, 1)[1]
                next_month = 1
                next_year = request_year + 1
            min_date = datetime.datetime.strptime(interval, "%Y-%m-%d")
            if request_day == current_days:
                if request_month == 11:
                    max_date = datetime.datetime.strptime(
                        f'{next_year + 1}-{"01"}-{"01"}', "%Y-%m-%d"
                    )
                    dict_obj = [
                        min_date.strftime("%Y-%m-%d"),
                        max_date.strftime("%Y-%m-%d"),
                    ]
                else:
                    max_date = datetime.datetime.strptime(
                        f'{next_year}-{next_month + 1}-{"01"}', "%Y-%m-%d"
                    )
                    dict_obj = [
                        min_date.strftime("%Y-%m-%d"),
                        max_date.strftime("%Y-%m-%d"),
                    ]
            else:
                max_date = datetime.datetime.strptime(
                    f'{next_year}-{next_month}-{"01"}', "%Y-%m-%d"
                )
                dict_obj = [
                    min_date.strftime("%Y-%m-%d"),
                    max_date.strftime("%Y-%m-%d"),
                ]
            return JsonResponse(dict_obj, safe=False)
        if employee:
            return JsonResponse(division, safe=False)
        return super(OfficialMemoAdd, self).get(request, *args, **kwargs)


class OfficialMemoDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = OfficialMemo
    permission_required = "hrdepartment_app.view_officialmemo"

    def get_context_data(self, **kwargs):
        content = super().get_context_data(**kwargs)
        content["change_history"] = get_history(self, OfficialMemo)
        return content


class OfficialMemoCancel(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    permission_required = "hrdepartment_app.change_officialmemo"
    template_name = "hrdepartment_app/officialmemo_form_cancel.html"
    form_class = OficialMemoCancelForm

    def get_context_data(self, **kwargs):
        content = super().get_context_data(**kwargs)
        content["change_history"] = get_history(self, OfficialMemo)
        return content

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:memo_list")

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        try:
            if self.object.docs:
                cancel = False
        except ApprovalOficialMemoProcess.DoesNotExist:
            cancel = True
        kwargs.update({"cancel": cancel})
        return kwargs


class OfficialMemoUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    template_name = "hrdepartment_app/officialmemo_form_update.html"
    permission_required = "hrdepartment_app.change_officialmemo"

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        # Получаем объект
        obj_item = self.get_object()
        obj_list = OfficialMemo.objects.filter(
            Q(person=obj_item.person)
            & Q(official_memo_type="1")
            & Q(docs__accepted_accounting=False)
        )
        # Получаем разницу в днях, для определения количества дней СП
        delta = self.object.period_for - self.object.period_from
        # Передаем количество дней в контекст
        content["period"] = int(delta.days) + 1
        # Получаем все служебные записки по человеку, исключая текущую
        filters = (
            OfficialMemo.objects.filter(person=self.object.person)
            .exclude(pk=self.object.pk)
            .exclude(cancellation=True)
        )
        filter_string = {
            "pk": 0,
            "period": datetime.datetime.strptime("1900-01-01", "%Y-%m-%d").date(),
        }
        # Проходимся по выборке в цикле
        for item in filters:
            if item.period_for > filter_string["period"]:
                filter_string["pk"] = item.pk
                filter_string["period"] = item.period_for

        content["form"].fields[
            "place_production_activity"
        ].queryset = PlaceProductionActivity.objects.all()
        if obj_item.official_memo_type == "2":
            content["form"].fields["document_extension"].queryset = obj_list
        else:
            content["form"].fields[
                "document_extension"
            ].queryset = OfficialMemo.objects.filter(pk=0).exclude(cancellation=True)
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.object}"
        content["change_history"] = get_history(self, OfficialMemo)
        return content

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:memo_list")

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)

    def form_valid(self, form):
        critical_change = 0
        warning_change = 0

        def person_finder(item, instanse_obj):
            person_list = ["person_id"]
            date_field = ["period_from", "period_for"]
            if item in person_list:
                return DataBaseUser.objects.get(pk=instanse_obj[item])
            if item in date_field:
                return instanse_obj[item].strftime("%d.%m.%Y")
            if item == "purpose_trip_id":
                return Purpose.objects.get(pk=instanse_obj[item])
            else:
                return instanse_obj[item]

        if form.is_valid():
            # в old_instance сохраняем старые значения записи
            object_item = self.get_object()
            place_old = set(
                [item.name for item in object_item.place_production_activity.all()]
            )

            old_instance = object_item.__dict__
            refresh_form = form.save(commit=False)
            if refresh_form.official_memo_type == "1":
                refresh_form.document_extension = None
            refresh_form.save()
            form.save_m2m()
            object_item = self.get_object()
            # в new_instance сохраняем новые значения записи
            new_instance = object_item.__dict__
            place_new = set(
                [item.name for item in object_item.place_production_activity.all()]
            )
            changed = False
            # создаем генератор списка
            diffkeys = [k for k in old_instance if old_instance[k] != new_instance[k]]
            message = (
                "<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:<br>"
            )
            # print(diffkeys)
            if place_old != place_new:
                critical_change = 1
                message += (
                    f"Место назначения: <strike>{place_old}</strike> -> {place_new}<br>"
                )
                changed = True
            # Доработать замену СЗ
            for k in diffkeys:
                # print(k)
                if k != "_state":
                    # if object_item._meta.get_field(k).verbose_name == 'Сотрудник':
                    #     critical_change = 1
                    # if object_item._meta.get_field(k).verbose_name == 'Дата начала':
                    #     if new_instance[k] < old_instance[k]:
                    #         critical_change = 1
                    #     else:
                    #         warning_change = 1
                    # if object_item._meta.get_field(k).verbose_name == 'Дата окончания':
                    #     if (new_instance[k] != old_instance[k]) and (
                    #             str(object_item.purpose_trip) == 'Прохождения курсов повышения квалификации (КПК)'):
                    #         warning_change = 1
                    if k == "person_id":
                        critical_change = 1
                    if k == "period_from":
                        if new_instance[k] < old_instance[k]:
                            critical_change = 1
                        else:
                            warning_change = 1
                    if k == "period_for":
                        if (new_instance[k] != old_instance[k]) and (
                                str(object_item.purpose_trip)
                                == "Прохождения курсов повышения квалификации (КПК)"
                        ):
                            critical_change = 1
                        warning_change = 1
                    if k == "type_trip":
                        warning_change = 1
                    if k == "purpose_trip_id":
                        warning_change = 1
                    message += f"{object_item._meta.get_field(k).verbose_name}: <strike>{person_finder(k, old_instance)}</strike> -> {person_finder(k, new_instance)}<br>"
                    changed = True
            get_obj = self.get_object()

            if changed:
                object_item.history_change.create(
                    author=self.request.user, body=message
                )
                if critical_change == 1:
                    try:
                        get_bpmemo_obj = ApprovalOficialMemoProcess.objects.get(
                            pk=object_item.docs.pk
                        )
                        if object_item.order:
                            get_order_obj = object_item.order
                        else:
                            get_order_obj = ""
                        if get_order_obj != "":
                            # ToDo: Сделать обработку отправки письма
                            send_mail_change(1, get_obj, message)
                            if get_obj.period_for < datetime.datetime.now().date():
                                get_bpmemo_obj.location_selected = False
                                get_bpmemo_obj.accommodation = ""
                                get_obj.accommodation = ""
                            get_bpmemo_obj.process_accepted = False
                            get_bpmemo_obj.email_send = False
                            get_bpmemo_obj.order = None
                            get_bpmemo_obj.originals_received = False
                            get_bpmemo_obj.hr_accepted = False
                            get_bpmemo_obj.accepted_accounting = False
                            get_order_obj.cancellation = True
                            get_obj.document_accepted = False
                            get_obj.order = None
                            get_obj.comments = "Документ согласован"
                            get_obj.save()
                            get_bpmemo_obj.save()
                            get_order_obj.save()
                        else:
                            # ToDo: Сделать обработку отправки письма
                            send_mail_change(2, get_obj, message)
                            get_bpmemo_obj.location_selected = False
                            get_bpmemo_obj.accommodation = ""
                            get_obj.comments = "Документ согласован"
                            get_obj.save()
                            get_bpmemo_obj.save()
                    except Exception as _ex:
                        print(_ex)
                else:
                    if warning_change == 1:
                        send_mail_change(3, get_obj, message)
            return HttpResponseRedirect(reverse("hrdepartment_app:memo_list"))

        else:
            logger.info(f"{form.errors}")

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get("employee", None)
        period_from = request.GET.get("period_from", None)
        memo_type = request.GET.get("memo_type", None)
        """
        Функция memo_type_change() в officialmemo_form_update.html. Если в качестве типа служебной записки указывается
        продление, то происходит выборка служебных записок с полями Сотрудник = Сотрудник, Тип СЗ = направление
        и поле Принят в бухгалтерию у бизнес процесса по этим СЗ не равно Истина. Поле документ основание заполняется 
        и в форме появляется возможность выбора
        """
        if memo_type and employee:
            if memo_type == "2":
                memo_list = (
                    OfficialMemo.objects.filter(
                        Q(person=employee)
                        & Q(official_memo_type="1")
                        & Q(docs__accepted_accounting=False)
                    )
                    .exclude(pk=self.get_object().pk)
                    .exclude(cancelation=True)
                )
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                return JsonResponse(memo_obj_list)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, "%Y-%m-%d")
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date)
            ).exclude(cancelation=True)
            try:
                filter_string = datetime.datetime.strptime(
                    "1900-01-01", "%Y-%m-%d"
                ).date()
                for item in filters:
                    if item.period_for > filter_string:
                        filter_string = item.period_for
            except AttributeError:
                logger.info(
                    f"За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}"
                )
            if filters.count() > 0:
                html = filter_string + datetime.timedelta(days=1)
                return JsonResponse(html, safe=False)
        # Согласно приказу, ограничиваем последним днем предыдущего и первым днем следующего месяцев
        interval = request.GET.get("interval", None)
        period_for_value = request.GET.get("pfv", None)
        if interval:
            request_day = datetime.datetime.strptime(interval, "%Y-%m-%d").day
            request_month = datetime.datetime.strptime(interval, "%Y-%m-%d").month
            request_year = datetime.datetime.strptime(interval, "%Y-%m-%d").year
            current_days = monthrange(request_year, request_month)[1]

            if request_month < 12:
                next_days = monthrange(request_year, request_month + 1)[1]
                next_month = request_month + 1
                next_year = request_year
            else:
                next_days = monthrange(request_year + 1, 1)[1]
                next_month = 1
                next_year = request_year + 1
            min_date = datetime.datetime.strptime(interval, "%Y-%m-%d")
            if request_day == current_days:
                if request_month == 11:
                    max_date = datetime.datetime.strptime(
                        f'{next_year + 1}-{"01"}-{"01"}', "%Y-%m-%d"
                    )
                    dict_obj = [
                        min_date.strftime("%Y-%m-%d"),
                        max_date.strftime("%Y-%m-%d"),
                    ]
                else:
                    max_date = datetime.datetime.strptime(
                        f'{next_year}-{next_month + 1}-{"01"}', "%Y-%m-%d"
                    )
                    dict_obj = [
                        min_date.strftime("%Y-%m-%d"),
                        max_date.strftime("%Y-%m-%d"),
                    ]
            else:
                max_date = datetime.datetime.strptime(
                    f'{next_year}-{next_month}-{"01"}', "%Y-%m-%d"
                )
                dict_obj = [
                    min_date.strftime("%Y-%m-%d"),
                    max_date.strftime("%Y-%m-%d"),
                ]
            if datetime.datetime.strptime(period_for_value, "%Y-%m-%d") > max_date:
                # period_for_value = max_date
                dict_obj.append(max_date)
            else:
                dict_obj.append(period_for_value)
            return JsonResponse(dict_obj, safe=False)
        return super(OfficialMemoUpdate, self).get(request, *args, **kwargs)


class ApprovalOficialMemoProcessList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess
    permission_required = "hrdepartment_app.view_approvaloficialmemoprocess"
    paginate_by = 10
    ordering = "-id"

    def get_queryset(self):
        qs = super(ApprovalOficialMemoProcessList, self).get_queryset()
        if not self.request.user.is_superuser:
            user_division = DataBaseUser.objects.get(
                pk=self.request.user.pk
            ).user_work_profile.divisions

            qs = ApprovalOficialMemoProcess.objects.filter(
                Q(person_agreement__user_work_profile__divisions=user_division)
                | Q(person_distributor__user_work_profile__divisions=user_division)
                | Q(person_executor__user_work_profile__divisions=user_division)
                | Q(person_department_staff__user_work_profile__divisions=user_division)
            )
        return qs

    def get(self, request, *args, **kwargs):
        # # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        # id_all = request.GET.get("id_all", None)
        # # Подготавливаем запросную строку

        # match id_all:
        #     case "1":
        #         query &= Q(cancellation=False)
        #         query &= Q(document_not_agreed=False)
        #     case "2":
        #         query &= Q(cancellation=False)
        #         query &= ~Q(document__official_memo_type=3)  # ~Q это отрицание, т.е. исключение
        #         query &= Q(document_not_agreed=True)
        #         query &= Q(location_selected=False)
        #     case "3":
        #         query &= Q(cancellation=False)
        #         query &= Q(location_selected=True)
        #         query &= Q(process_accepted=False)
        #     case "4":
        #         query &= Q(cancellation=False)
        #         query &= ~Q(document__official_memo_type=2)  # ~Q это отрицание, т.е. исключение
        #         query &= Q(process_accepted=True)
        #         query &= Q(originals_received=False)
        #     case "5":
        #         query &= Q(cancellation=False)
        #         query &= Q(originals_received=True)
        #         query &= Q(hr_accepted=False)
        #     case "6":
        #         query &= Q(cancellation=False)
        #         query &= Q(hr_accepted=True)
        #         query &= Q(accepted_accounting=False)
        #     case "7":
        #         query &= Q(cancellation=False)
        #         query &= Q(accepted_accounting=True)
        #     case "8":
        #         pass
        #     case _:
        #         query &= Q(cancellation=False)
        #         query &= Q(accepted_accounting=False)
        #
        # if not request.user.is_superuser:
        #     if request.user.user_work_profile.job.division_affiliation.pk != 1:
        #         query &= Q(person_executor__user_work_profile__job__division_affiliation__pk=
        #                    request.user.user_work_profile.job.division_affiliation.pk)
        # if request.headers.get("x-requested-with") == "XMLHttpRequest":
        #     approvalmemo_list = ApprovalOficialMemoProcess.objects.filter(query)
        #     data = [approvalmemo_item.get_data() for approvalmemo_item in approvalmemo_list]
        #     response = {"data": data}
        #     return JsonResponse(response)

        """ 
            "document",
            "submit_for_approval",
            "document_not_agreed",
            "location_selected",
            "process_accepted",
            "accepted_accounting",
            "accommodation",
            "order",
            "comments",  
        """
        query = Q()
        if not request.user.is_superuser:
            if request.user.user_work_profile.job.division_affiliation.pk != 1:
                query &= Q(person_executor__user_work_profile__job__division_affiliation__pk=
                           request.user.user_work_profile.job.division_affiliation.pk)
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['document__title', 'person_executor__title',
                           'person_agreement__title', 'person_distributor__title',
                           'person_department_staff__title', 'person_accounting__title',
                           'accommodation', 'order__document_number', 'document__comments',
                           ]
            context = ajax_search(request, self, search_list, ApprovalOficialMemoProcess, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Бизнес процесс по служебным поездкам"
        return context


class ApprovalOficialMemoProcessAdd(
    PermissionRequiredMixin, LoginRequiredMixin, CreateView
):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm
    permission_required = "hrdepartment_app.add_approvaloficialmemoprocess"

    def get_context_data(self, **kwargs):
        global person_agreement_list
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)
        content["form"].fields["document"].queryset = OfficialMemo.objects.filter(
            Q(docs__isnull=True) & Q(responsible=self.request.user)
        ).exclude(cancellation=True)
        business_process = BusinessProcessDirection.objects.filter(
            person_executor=self.request.user.user_work_profile.job
        )
        users_list = (
            DataBaseUser.objects.all()
            .exclude(username="proxmox")
            .exclude(is_active=False)
        )
        # Для поля Исполнитель, делаем выборку пользователя из БД на основе request
        content["form"].fields["person_executor"].queryset = users_list.filter(
            pk=self.request.user.pk
        )

        person_agreement_list = list()
        content["form"].fields["person_agreement"].queryset = users_list.filter(
            user_work_profile__job__pk__in=person_agreement_list
        )
        for item in business_process:
            if item.person_executor.filter(
                    name__contains=self.request.user.user_work_profile.job.name
            ):
                person_agreement_list = [
                    items[0] for items in item.person_agreement.values_list()
                ]
                content["form"].fields["person_agreement"].queryset = users_list.filter(
                    user_work_profile__job__pk__in=person_agreement_list
                )
        # content['form'].fields['person_distributor'].queryset = users_list.filter(
        #     Q(user_work_profile__divisions__type_of_role='1') & Q(user_work_profile__job__right_to_approval=True) &
        #     Q(is_superuser=False))
        # content['form'].fields['person_department_staff'].queryset = users_list.filter(
        #     Q(user_work_profile__divisions__type_of_role='2') & Q(user_work_profile__job__right_to_approval=True) &
        #     Q(is_superuser=False))
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить бизнес процесс"
        return content

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:bpmemo_list")

    def form_valid(self, form):
        if form.is_valid():
            refresh_form = form.save(commit=False)
            refresh_form.start_date_trip = refresh_form.document.period_from
            refresh_form.end_date_trip = refresh_form.document.period_for
            refresh_form.save()
        return super().form_valid(form)


class ApprovalOficialMemoProcessUpdate(
    PermissionRequiredMixin, LoginRequiredMixin, UpdateView
):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessUpdateForm
    template_name = "hrdepartment_app/approvaloficialmemoprocess_form_update.html"
    permission_required = "hrdepartment_app.change_approvaloficialmemoprocess"

    def get_queryset(self):
        qs = ApprovalOficialMemoProcess.objects.all().select_related(
            "person_executor",
            "person_agreement",
            "person_distributor",
            "person_department_staff",
            "person_clerk",
            "person_hr",
            "person_accounting",
            "document",
            "order",
        )
        return qs

    def get_context_data(self, **kwargs):
        global person_agreement_list

        users_list = (
            DataBaseUser.objects.all()
            .exclude(username="proxmox")
            .exclude(is_active=False)
        )
        content = super(ApprovalOficialMemoProcessUpdate, self).get_context_data(
            **kwargs
        )
        document = self.get_object()
        business_process = BusinessProcessDirection.objects.filter(
            Q(person_executor=document.person_executor.user_work_profile.job) & Q(business_process_type=1)
        )
        content["document"] = document.document
        person_agreement_list = list()
        person_clerk_list = list()
        person_hr_list = list()
        for item in business_process:
            person_agreement_list = [
                items[0] for items in item.person_agreement.values_list()
            ]
            person_clerk_list = [items[0] for items in item.clerk.values_list()]
            person_hr_list = [items[0] for items in item.person_hr.values_list()]
        # Получаем подразделение исполнителя
        # division = document.person_executor.user_work_profile.divisions
        # При редактировании БП фильтруем поле исполнителя, чтоб нельзя было изменить его в процессе работы
        content["form"].fields["person_executor"].queryset = users_list.filter(
            pk=document.person_executor.pk
        )
        # Если установлен признак согласования документа, то фильтруем поле согласующего лица
        if document.document_not_agreed:
            try:
                content["form"].fields["person_agreement"].queryset = users_list.filter(
                    pk=document.person_agreement.pk
                )
            except AttributeError:
                content["form"].fields["person_agreement"].queryset = users_list.filter(
                    user_work_profile__job__pk__in=person_agreement_list
                )
        else:
            # Иначе по подразделению исполнителя фильтруем руководителей для согласования
            content["form"].fields["person_agreement"].queryset = users_list.filter(
                user_work_profile__job__pk__in=person_agreement_list
            )
            try:
                # Если пользователь = Согласующее лицо
                if self.request.user.user_work_profile.job.pk in person_agreement_list:
                    content["form"].fields[
                        "person_agreement"
                    ].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_agreement_list)
                        & Q(pk=self.request.user.pk)
                    )
                # Иначе весь список согласующих лиц
                else:
                    content["form"].fields[
                        "person_agreement"
                    ].queryset = users_list.filter(
                        user_work_profile__job__pk__in=person_agreement_list
                    )
            except AttributeError as _ex:
                logger.error(f"У пользователя отсутствует должность")
                # ToDo: Нужно вставить выдачу ошибки
                return {}

        list_agreement = list()
        for unit in users_list.filter(
                user_work_profile__job__pk__in=person_agreement_list
        ):
            list_agreement.append(unit.pk)
        content["list_agreement"] = list_agreement

        list_distributor = users_list.filter(
            Q(user_work_profile__divisions__type_of_role="1")
            & Q(user_work_profile__job__right_to_approval=True)
            # & Q(is_superuser=False)
        )

        content["form"].fields["person_distributor"].queryset = list_distributor
        content["list_distributor"] = list_distributor

        list_department_staff = users_list.filter(
            Q(user_work_profile__divisions__type_of_role="2")
            & Q(user_work_profile__job__right_to_approval=True)
            & Q(is_superuser=False)
        )
        content["form"].fields[
            "person_department_staff"
        ].queryset = list_department_staff
        content["list_department_staff"] = list_department_staff

        list_accounting = users_list.filter(
            Q(user_work_profile__divisions__type_of_role="3")
            & Q(user_work_profile__job__right_to_approval=True)
            & Q(is_superuser=False)
        )
        content["form"].fields["person_accounting"].queryset = list_accounting
        content["list_accounting"] = list_accounting

        list_clerk = users_list.filter(user_work_profile__job__pk__in=person_clerk_list)
        if document.originals_received:
            try:
                content["form"].fields["person_clerk"].queryset = users_list.filter(
                    pk=document.person_clerk.pk
                )
            except AttributeError:
                content["form"].fields["person_clerk"].queryset = list_clerk
        else:
            # Иначе по подразделению исполнителя фильтруем делопроизводителя для согласования
            content["form"].fields["person_clerk"].queryset = list_clerk
            try:
                # Если пользователь = Делопроизводитель
                if self.request.user.user_work_profile.job.pk in person_clerk_list:
                    content["form"].fields["person_clerk"].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_clerk_list)
                        & Q(pk=self.request.user.pk)
                    )
                # Иначе весь список делопроизводителей
                else:
                    content["form"].fields["person_clerk"].queryset = list_clerk
            except AttributeError as _ex:
                logger.error(f"У пользователя отсутствует должность")
                # ToDo: Нужно вставить выдачу ошибки
                return {}
        content["list_clerk"] = list_clerk

        list_hr = users_list.filter(user_work_profile__job__pk__in=person_hr_list)
        if document.originals_received:
            try:
                content["form"].fields["person_hr"].queryset = users_list.filter(
                    pk=document.person_hr.pk
                )
            except AttributeError:
                content["form"].fields["person_hr"].queryset = list_hr
        else:
            # Иначе по подразделению исполнителя фильтруем сотрудника ОК для согласования
            content["form"].fields["person_hr"].queryset = list_hr
            try:
                # Если пользователь = Сотрудник ОК
                if self.request.user.user_work_profile.job.pk in person_hr_list:
                    content["form"].fields["person_hr"].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_hr_list)
                        & Q(pk=self.request.user.pk)
                    )
                # Иначе весь список сотрудников ОК
                else:
                    content["form"].fields["person_hr"].queryset = list_hr
            except AttributeError as _ex:
                logger.error(f"У пользователя отсутствует должность")
                # ToDo: Нужно вставить выдачу ошибки
                return {}
        content["list_hr"] = list_hr

        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {document.document.title}"
        # Выбираем приказ
        if document.document.official_memo_type == "1":
            content["form"].fields["order"].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.pk
            ).exclude(cancellation=True)
        elif document.document.official_memo_type == "2":
            content["form"].fields["order"].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.pk
            ).exclude(cancellation=True)
        else:
            content["form"].fields["order"].queryset = DocumentsOrder.objects.filter(
                pk=0
            )
        delta = document.document.period_for - document.document.period_from
        content["ending_day"] = ending_day(int(delta.days) + 1)
        content["change_history"] = get_history(self, ApprovalOficialMemoProcess)
        content["without_departure"] = (
            False if document.document.official_memo_type == "3" else True
        )
        content["extension"] = (
            False if document.document.official_memo_type == "2" else True
        )
        # print(document.prepaid_expense_summ - (document.number_business_trip_days*500 + document.number_flight_days*900))
        return content

    def form_valid(self, form):
        def person_finder(object_item, item, instanse_obj):
            person_list = [
                "Исполнитель",
                "Согласующее лицо",
                "Сотрудник НО",
                "Сотрудник ОК",
                "Сотрудник Бухгалтерии",
                "Делопроизводитель",
            ]
            if object_item._meta.get_field(k).verbose_name in person_list:
                if instanse_obj[item]:
                    return DataBaseUser.objects.get(pk=instanse_obj[item])
                else:
                    return "Пустое значение"
            else:
                if instanse_obj[item] == True:
                    return "Да"
                elif instanse_obj[item] == False:
                    return "Нет"
                else:
                    return instanse_obj[item]

        if form.is_valid():
            object_item = self.get_object()
            # в old_instance сохраняем старые значения записи
            old_instance = object_item.__dict__
            if object_item.document.official_memo_type == "2":
                refresh_form = form.save(commit=False)
                refresh_form.hr_accepted = object_item.hr_accepted
                refresh_form.person_accounting = object_item.person_accounting
                refresh_form.accepted_accounting = object_item.accepted_accounting
                refresh_form.date_receipt_original = object_item.date_receipt_original
                refresh_form.submitted_for_signature = (
                    object_item.submitted_for_signature
                )
                refresh_form.date_transfer_hr = object_item.date_transfer_hr
                refresh_form.number_business_trip_days = (
                    object_item.number_business_trip_days
                )
                refresh_form.number_flight_days = object_item.number_flight_days
                refresh_form.person_hr = object_item.person_hr
                refresh_form.start_date_trip = object_item.start_date_trip
                refresh_form.end_date_trip = object_item.end_date_trip
                refresh_form.date_transfer_accounting = (
                    object_item.date_transfer_accounting
                )
                refresh_form.prepaid_expense_summ = object_item.prepaid_expense_summ
                refresh_form.save()
            else:
                form.save()
            object_item = self.get_object()
            """
            Если проверено отделом бухгалтерией и документооборот завершен, то выбираем все продления и также 
            закрываем их.
            """
            if object_item.accepted_accounting:
                doc_list = object_item.document.extension.all()
                for item in doc_list:
                    try:
                        approval_process_item = ApprovalOficialMemoProcess.objects.get(
                            document=item
                        )
                        approval_process_item.hr_accepted = object_item.hr_accepted
                        approval_process_item.person_accounting = (
                            object_item.person_accounting
                        )
                        approval_process_item.accepted_accounting = (
                            object_item.accepted_accounting
                        )
                        approval_process_item.date_receipt_original = (
                            object_item.date_receipt_original
                        )
                        approval_process_item.submitted_for_signature = (
                            object_item.submitted_for_signature
                        )
                        approval_process_item.date_transfer_hr = (
                            object_item.date_transfer_hr
                        )
                        approval_process_item.number_business_trip_days = (
                            object_item.number_business_trip_days
                        )
                        approval_process_item.number_flight_days = (
                            object_item.number_flight_days
                        )
                        approval_process_item.person_hr = object_item.person_hr
                        approval_process_item.start_date_trip = item.period_from
                        approval_process_item.end_date_trip = object_item.end_date_trip
                        approval_process_item.date_transfer_accounting = (
                            object_item.date_transfer_accounting
                        )
                        approval_process_item.prepaid_expense_summ = (
                            object_item.prepaid_expense_summ
                        )
                        document = approval_process_item.document
                        document.comments = "Документооборот завершен"
                        document.save()
                        approval_process_item.save()
                    except Exception as _ex:
                        logger.warning(f"{_ex}: Документ - {object_item}")
            # в new_instance сохраняем новые значения записи
            new_instance = object_item.__dict__
            changed = False
            # создаем генератор списка
            diffkeys = [k for k in old_instance if old_instance[k] != new_instance[k]]
            message = "<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:\n"
            for k in diffkeys:
                if k != "_state":
                    message += f"{object_item._meta.get_field(k).verbose_name}: <strike>{person_finder(object_item, k, old_instance)}</strike> -> {person_finder(object_item, k, new_instance)}\n"
                    changed = True
            if changed:
                object_item.history_change.create(
                    author=self.request.user, body=message
                )

            return HttpResponseRedirect(reverse("hrdepartment_app:bpmemo_list"))
        else:
            logger.info(f"{form.errors}")

    # Проверяем изменения параметров
    def post(self, request, *args, **kwargs):
        """
        Обрабатываем POST запрос. Получаем данные передаваемые в форме. Внутренние переменные:
        data - Дата приказа; number - Номер приказа; accommodation - место проживания; change_status - статус изменения
        документа, 0 - если данные документа не менялись, и 1 - если данные были изменены, document - ссылка на
        служебную записку.

        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        order = request.POST.get("order")
        accommodation = request.POST.get("accommodation")
        change_status = 0
        document = OfficialMemo.objects.get(pk=self.get_object().document.pk)
        if document.order != order:
            # Если добавлен или изменен приказ, сохраняем его в документ Служебной записки
            if order != "":
                document.order = DocumentsOrder.objects.get(pk=order)
                change_status = 1

        if document.accommodation != accommodation:
            # Если добавлено или изменено место проживания, сохраняем его в документ Служебной записки
            if accommodation:
                document.accommodation = accommodation
                change_status = 1

        if change_status > 0:
            if document.cancellation:
                document.comments = "Документ отменен"
            document.save()
        return super().post(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.GET.get("send") == "0":
            obj_item = self.get_object()
            obj_item.send_mail(title="Повторное уведомление", trigger=1)
        if request.GET.get("send") == "1":
            obj_item = self.get_object()
            obj_item.send_mail(title="Повторное уведомление", trigger=2)
            # return redirect('hrdepartment_app:bpmemo_update', obj_item.pk)
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy("hrdepartment_app:bpmemo_list")


class ApprovalOficialMemoProcessCancel(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessChangeForm
    template_name = "hrdepartment_app/approvaloficialmemoprocess_form_cancel.html"

    def form_valid(self, form):
        if form.is_valid():
            form.save()
            obj_item = self.get_object()
            official_memo = obj_item.document
            order = obj_item.order
            try:
                if official_memo:
                    OfficialMemo.objects.filter(pk=official_memo.pk).update(
                        cancellation=True,
                        reason_cancellation=obj_item.reason_cancellation,
                        comments="Документ отменен",
                    )
                if order:
                    DocumentsOrder.objects.filter(pk=order.pk).update(
                        cancellation=True,
                        reason_cancellation=obj_item.reason_cancellation,
                    )
                    print("Отменен")
                obj_item.send_mail(title="Уведомление об отмене")
            except Exception as _ex:
                logger.error(f"Ошибка при отмене БП {_ex}")

        return super().form_valid(form)


class ApprovalOficialMemoProcessReportList(LoginRequiredMixin, ListView):
    """
    Контроль закрытых служебных поездок
    """

    model = ApprovalOficialMemoProcess
    template_name = "hrdepartment_app/approvaloficialmemoprocess_report_list.html"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get("report_month")
        current_year = self.request.GET.get("report_year")
        if current_month and current_year:
            request.session["current_month"] = int(current_month)
            request.session["current_year"] = int(current_year)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session["current_month"] and request.session["current_year"]:
                start_date = datetime.date(
                    year=int(request.session["current_year"]),
                    month=int(request.session["current_month"]),
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )

                if (
                        request.user.is_superuser
                        or request.user.user_work_profile.job.division_affiliation.pk == 1
                ):
                    reportcard_list = (
                        ApprovalOficialMemoProcess.objects.filter(
                            Q(document__period_for__in=search_interval)
                        )
                        .exclude(
                            document__comments__in=[
                                "Документооборот завершен",
                                "Передано в ОК",
                                "Передано в бухгалтерию",
                            ]
                        )
                        .exclude(document__official_memo_type__in=["2", "3"])
                        .exclude(cancellation=True)
                        .order_by("document__period_for")
                        .reverse()
                    )
                else:
                    reportcard_list = (
                        ApprovalOficialMemoProcess.objects.filter(
                            Q(document__period_for__in=search_interval)
                            & Q(
                                person_executor__user_work_profile__job__division_affiliation__pk=request.user.user_work_profile.job.division_affiliation.pk
                            )
                        )
                        .exclude(
                            document__comments__in=[
                                "Документооборот завершен",
                                "Передано в ОК",
                                "Передано в бухгалтерию",
                            ]
                        )
                        .exclude(document__official_memo_type__in=["2", "3"])
                        .exclude(cancellation=True)
                        .order_by("document__period_for")
                        .reverse()
                    )

            else:
                start_date = datetime.date(
                    year=datetime.datetime.today().year,
                    month=datetime.datetime.today().month,
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                if (
                        request.user.is_superuser
                        or request.user.user_work_profile.job.division_affiliation == 1
                ):
                    reportcard_list = (
                        ApprovalOficialMemoProcess.objects.filter(
                            Q(document__period_for__in=search_interval)
                        )
                        .exclude(
                            document__comments__in=[
                                "Документооборот завершен",
                                "Передано в ОК",
                                "Передано в бухгалтерию",
                            ]
                        )
                        .exclude(document__official_memo_type__in=["2", "3"])
                        .exclude(cancellation=True)
                        .order_by("document__period_for")
                        .reverse()
                    )
                else:
                    reportcard_list = (
                        ApprovalOficialMemoProcess.objects.filter(
                            Q(document__period_for__in=search_interval)
                            & Q(
                                person_executor__user_work_profile__job__division_affiliation__pk=request.user.user_work_profile.job.division_affiliation.pk
                            )
                        )
                        .exclude(
                            document__comments__in=[
                                "Документооборот завершен",
                                "Передано в ОК",
                                "Передано в бухгалтерию",
                            ]
                        )
                        .exclude(document__official_memo_type__in=["2", "3"])
                        .exclude(cancellation=True)
                        .order_by("document__period_for")
                        .reverse()
                    )
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["current_year"] = self.request.session["current_year"]
        context["current_month"] = str(self.request.session["current_month"])
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Бизнес процессы списком"
        return context


class PurposeList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = Purpose
    permission_required = "hrdepartment_app.view_purpose"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            purpose_list = Purpose.objects.all()
            data = [purpose_item.get_data() for purpose_item in purpose_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Цели служебных поездок"
        return context


class PurposeAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = Purpose
    form_class = PurposeAddForm
    permission_required = "hrdepartment_app.add_purpose"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить цель СП"
        return context


class PurposeUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Purpose
    form_class = PurposeUpdateForm
    permission_required = "hrdepartment_app.change_purpose"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context


class BusinessProcessDirectionList(
    PermissionRequiredMixin, LoginRequiredMixin, ListView
):
    model = BusinessProcessDirection
    permission_required = "hrdepartment_app.view_businessprocessdirection"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Направление бизнес-процессов"
        return context


class BusinessProcessDirectionAdd(
    PermissionRequiredMixin, LoginRequiredMixin, CreateView
):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionAddForm
    permission_required = "hrdepartment_app.add_businessprocessdirection"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить направление бизнес процесса"
        return context


class BusinessProcessDirectionUpdate(
    PermissionRequiredMixin, LoginRequiredMixin, UpdateView
):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionUpdateForm
    permission_required = "hrdepartment_app.change_businessprocessdirection"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context


class ReportApprovalOficialMemoProcessList(
    PermissionRequiredMixin, LoginRequiredMixin, ListView
):
    """
    Отчет по сотрудникам
    """

    model = ApprovalOficialMemoProcess
    template_name = "hrdepartment_app/reportapprovaloficialmemoprocess_list.html"
    permission_required = "hrdepartment_app.view_approvaloficialmemoprocess"

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse("hrdepartment_app:bpmemo_report"))

    def get_queryset(self):
        qs = super(ReportApprovalOficialMemoProcessList, self).get_queryset()
        return qs

    def get(self, request, *args, **kwargs):
        # Получаем выборку из базы данных, если был изменен один из параметров

        if self.request.GET:
            current_year = int(self.request.GET.get("CY"))
            current_month = int(self.request.GET.get("CM"))
            current_person = self.request.GET.get("CP")

            html_obj = ""
            report = []
            from calendar import monthrange

            days = monthrange(current_year, current_month)[1]
            date_start = datetime.datetime.strptime(
                f"{current_year}-{current_month}-01", "%Y-%m-%d"
            )
            date_end = datetime.datetime.strptime(
                f"{current_year}-{current_month}-{days}", "%Y-%m-%d"
            )
            current_person_list = current_person.split("&")
            if self.request.user.user_work_profile.divisions.type_of_role == "2":
                if len(current_person) > 0:
                    report_query = ReportCard.objects.filter(
                        Q(report_card_day__gte=date_start)
                        & Q(report_card_day__lte=date_end)
                        & Q(employee__pk__in=current_person_list)
                    ).order_by("employee__last_name")
                else:
                    report_query = ReportCard.objects.filter(
                        Q(report_card_day__gte=date_start)
                        & Q(report_card_day__lte=date_end)
                    ).order_by("employee__last_name")
                # for item in range(0, 4):
                #     count_obj = ApprovalOficialMemoProcess.objects.filter(
                #         (Q(start_date_trip__lte=date_start) | Q(start_date_trip__lte=date_end))
                #         & Q(end_date_trip__gte=date_start) & Q(
                #             document__person__user_work_profile__job__type_of_job=str(item))).exclude(
                #         cancellation=True).order_by(
                #         'document__responsible').count()
                #     report.append(count_obj)
            else:
                report_query = ReportCard.objects.filter(
                    Q(
                        employee__user_work_profile__job__division_affiliation__pk=self.request.user.user_work_profile.job.division_affiliation.pk
                    )
                    & Q(report_card_day__gte=date_start)
                    & Q(report_card_day__lte=date_end)
                    & Q(employee__pk__in=current_person_list)
                ).order_by("employee__last_name")
            dict_obj = dict()
            dist = report_query.values("employee__title").distinct()
            for rec in dist:
                list_obj = []
                selected_record = report_query.filter(
                    employee__title=rec["employee__title"]
                )
                person = format_name_initials(rec["employee__title"])
                if person not in dict_obj:
                    dict_obj[person] = []
                for days_count in range(0, (date_end - date_start).days + 1):
                    place, place_short = "", ""
                    curent_day = date_start + datetime.timedelta(days_count)
                    if selected_record.filter(
                            report_card_day=curent_day.date()
                    ).exists():
                        if (
                                selected_record.filter(
                                    report_card_day=curent_day.date()
                                ).count()
                                == 1
                        ):
                            obj = selected_record.filter(
                                report_card_day=curent_day.date()
                            ).first()
                            place = "; ".join(
                                [item.name for item in obj.place_report_card.all()]
                            )
                            if place == "":
                                place = obj.get_record_type_display()
                            trigger = "2" if obj.confirmed else "1"
                            list_obj.append([trigger, place, obj.record_type])
                        else:
                            for item in selected_record.filter(
                                    report_card_day=curent_day.date()
                            ):
                                place += item.get_record_type_display() + "; "
                                place_short += item.record_type + "; "
                            trigger = "3"
                            list_obj.append([trigger, place, place_short])
                            # print(place_short)
                    else:
                        list_obj.append(["0", "", ""])

                dict_obj[person] = list_obj

                table_set = dict_obj
                html_table_count = ""
                table_count = range(1, (date_end - date_start).days + 2)
                for item in table_count:
                    html_table_count += f'<th width="2%" style="position: -webkit-sticky;  position: sticky;  top: -3px; z-index: 2; background: #ffffff"><span style="color: #0a53be">{item}</span></th>'
                html_table_set = ""
                color = [
                    "f5f5dc",
                    "49c144",
                    "ff0000",
                    "a0dfbd",
                    "FFCC00",
                    "ffff00",
                    "9d76f5",
                    "ff8fa2",
                    "808080",
                    "76e3f5",
                    "46aef2",
                    "e8ef2a",
                    "fafafa",
                ]
                for key, value in table_set.items():
                    html_table_set += f'<tr><td width="14%" style="position: -webkit-sticky;  position: sticky;"><strong>{key}</strong></td>'
                    for unit in value:
                        match unit[0]:
                            case "1":
                                place = unit[1].replace('"', "")
                                match unit[2]:
                                    case "1":
                                        place_short = "Я"
                                        cnt = 12
                                    case "4":
                                        place_short = "БС"
                                        cnt = 10
                                    case "13":
                                        place_short = "Р"
                                        cnt = 12
                                    case "14":
                                        place_short = "СП"
                                        cnt = 3
                                    case "15":
                                        place_short = "К"
                                        cnt = 3
                                    case "2":
                                        place_short = "О"
                                        cnt = 9
                                    case "3" | "5" | "7" | "10" | "11":
                                        place_short = "ДО"
                                        cnt = 10
                                    case "16":
                                        place_short = "Б"
                                        cnt = 6
                                    case "17":
                                        place_short = "М"
                                        cnt = 7
                                    case "18":
                                        place_short = "ГО"
                                        cnt = 4
                                    case _:
                                        place_short = ""
                                        cnt = 8
                                html_table_set += f'<td width="2%" style="background-color: #{color[cnt]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}">{place_short}</td>'
                            case "2":
                                place = unit[1].replace('"', "")
                                match unit[2]:
                                    case "14":
                                        place_short = "СП"
                                        cnt = 1
                                    case "15":
                                        place_short = "К"
                                        cnt = 1
                                html_table_set += f'<td width="2%" style="background-color: #{color[cnt]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}"><strong>{place_short}</strong></td>'
                            case "3":
                                place = unit[1].replace('"', "")
                                place_short = ""
                                match unit[2]:
                                    case "1; 13; " | "13; 1; " | "1; 2; " | "2; 1; ":
                                        place_short = "Я"
                                        cnt = 12
                                    case "2; 18; " | "18; 2; ":
                                        place_short = "О"
                                        cnt = 9
                                    case "1; 16; " | "16; 1; ":
                                        place_short = "Б"
                                        cnt = 6
                                    case "17; 14; " | "17; 15; " | "15; 17; " | "14; 17; ":
                                        place_short = "М"
                                        cnt = 7
                                    case "1; 14; " | "14; 1; " | "13; 14; " | "14; 13; ":
                                        place_short = "СП"
                                        cnt = 1
                                    case "1; 15; " | "15; 1; " | "13; 15; " | "15; 13; ":
                                        place_short = "К"
                                        cnt = 1
                                    case _:
                                        cnt = 2
                                html_table_set += f'<td width="2%" style="background-color: #{color[cnt]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}"><strong>{place_short}</strong></td>'
                            case _:
                                html_table_set += f'<td width="2%" style="background-color: #{color[0]}; border-color:#4670ad;border-style:dashed;border-width:1px;"></td>'
                    html_table_set += "</tr>"

                job_type = {
                    "0": "Общий состав",
                    "1": "Летный состав",
                    "2": "Инженерный состав",
                    "3": "Транспортный отдел",
                }
                report_item_obj = f'<td colspan="{len(table_count) + 1}"><h4>'
                counter = 0
                for report_item in report:
                    report_item_obj += f"{job_type[str(counter)]}: {report_item};&nbsp;"
                    counter += 1
                report_item_obj += "</h4></td>"
                html_obj = f"""<table class="table table-ecommerce-simple table-striped mb-0" id="id_datatable" style="min-width: 1000px; display: block; overflow: auto;">
                                <thead>
                                <tr>{report_item_obj}</tr>
                                <tr>
                                    <th width="14%" style="position: -webkit-sticky;  position: sticky;  top: -3px; z-index: 2; background: #ffffff"><span style="color: #0a53be">ФИО</span></th>
                                    {html_table_count}
                                </tr>
                                </thead>
                                <tbody>
                                {html_table_set}
                                </tbody>
                            </table>"""

            return JsonResponse(html_obj, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        content = super().get_context_data(**kwargs)

        if self.request.GET:
            current_year = int(self.request.GET.get("CY"))
            current_month = int(self.request.GET.get("CM"))
        else:
            current_year = datetime.datetime.now().year
            current_month = datetime.datetime.now().month
        from calendar import monthrange

        days = monthrange(current_year, current_month)[1]
        date_start = datetime.datetime.strptime(
            f"{current_year}-{current_month}-01", "%Y-%m-%d"
        )
        date_end = datetime.datetime.strptime(
            f"{current_year}-{current_month}-{days}", "%Y-%m-%d"
        )

        # qs = ApprovalOficialMemoProcess.objects.filter(Q(person_executor__pk=self.request.user.pk) & (
        #         Q(document__period_from__lte=date_start) | Q(document__period_from__lte=date_end)) & Q(
        #     document__period_for__gte=date_start)).order_by('document__period_from')
        if self.request.user.user_work_profile.divisions.type_of_role == "2":
            qs = (
                ApprovalOficialMemoProcess.objects.filter(
                    (
                            Q(start_date_trip__lte=date_start)
                            | Q(start_date_trip__lte=date_end)
                    )
                    & Q(end_date_trip__gte=date_start)
                )
                .exclude(cancellation=True)
                .order_by("document__responsible")
            )
        else:
            qs = (
                ApprovalOficialMemoProcess.objects.filter(
                    Q(
                        person_executor__user_work_profile__job__division_affiliation__pk=self.request.user.user_work_profile.job.division_affiliation.pk
                    )
                    & (
                            Q(start_date_trip__lte=date_start)
                            | Q(start_date_trip__lte=date_end)
                    )
                    & Q(end_date_trip__gte=date_start)
                )
                .exclude(cancellation=True)
                .order_by("document__responsible")
            )
        dict_obj = dict()
        for item in qs.all().order_by("document__person__last_name"):
            list_obj = []
            person = format_name_initials(str(item.document.person))
            # Проверяем, заполнялся ли список по сотруднику
            if person in dict_obj:
                list_obj = dict_obj[person]
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    if item.hr_accepted:
                        if (
                                item.start_date_trip
                                <= curent_day.date()
                                <= item.end_date_trip
                        ):
                            list_obj[days_count] = "2"
                    else:
                        if (
                                item.document.period_from
                                <= curent_day.date()
                                <= item.document.period_for
                        ):
                            list_obj[days_count] = "1"
                dict_obj[format_name_initials(str(item.document.person))] = list_obj
            else:
                dict_obj[format_name_initials(str(item.document.person))] = []
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    # print(list_obj, days_count, date_end, date_start)
                    if item.hr_accepted:
                        if (
                                item.start_date_trip
                                <= curent_day.date()
                                <= item.end_date_trip
                        ):
                            list_obj.append(["2", ""])
                        else:
                            list_obj.append(["0", ""])
                    else:
                        if (
                                item.document.period_from
                                <= curent_day.date()
                                <= item.document.period_for
                        ):
                            list_obj.append(["1", ""])
                        else:
                            list_obj.append(["0", ""])

                dict_obj[format_name_initials(str(item.document.person))] = list_obj
        month_dict, year_dict = get_year_interval(2020)
        all_person = dict()
        if self.request.user.user_work_profile.divisions.type_of_role == "2":
            person = (
                DataBaseUser.objects.filter(is_active=True)
                .exclude(username="proxmox")
                .values("pk", "title")
                .order_by("last_name")
            )
        else:
            person = (
                DataBaseUser.objects.filter(
                    Q(is_active=True)
                    & Q(
                        user_work_profile__job__division_affiliation__pk=self.request.user.user_work_profile.job.division_affiliation.pk
                    )
                )
                .exclude(username="proxmox")
                .values("pk", "title")
                .order_by("last_name")
            )
        for item in person:
            all_person[item["pk"]] = item["title"]

        content["year_dict"] = year_dict
        content["month_dict"] = month_dict
        content["all_person"] = all_person
        content["table_set"] = dict_obj
        content["table_count"] = range(1, (date_end - date_start).days + 2)
        content["title"] = f"{PortalProperty.objects.all().last().portal_name} // Отчет"
        content["current_year"] = current_year
        content["current_month"] = current_month

        return content


# Должностные инструкции
class DocumentsJobDescriptionList(
    PermissionRequiredMixin, LoginRequiredMixin, ListView
):
    """
    Должностные инструкции - список
    """

    model = DocumentsJobDescription
    permission_required = "hrdepartment_app.view_documentsjobdescription"

    def get_queryset(self):
        return DocumentsJobDescription.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            documents_job_list = DocumentsJobDescription.objects.all()
            data = [
                documents_job_item.get_data()
                for documents_job_item in documents_job_list
            ]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Должностные инструкции"
        return context


class DocumentsJobDescriptionAdd(
    PermissionRequiredMixin, LoginRequiredMixin, CreateView
):
    """
    Должностные инструкции - создание
    """

    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionAddForm
    permission_required = "hrdepartment_app.add_documentsjobdescription"

    def get_context_data(self, *, object_list=None, **kwargs):
        content = super().get_context_data(object_list=None, **kwargs)
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить должностную инструкцию"
        return content

    # def get_form_kwargs(self):
    #     """
    #     Передаем в форму текущего пользователя. В форме переопределяем метод __init__
    #     :return: PK текущего пользователя
    #     """
    #     kwargs = super().get_form_kwargs()
    #     kwargs.update({"user": self.request.user.pk})
    #     return kwargs


class DocumentsJobDescriptionDetail(
    PermissionRequiredMixin, LoginRequiredMixin, DetailView
):
    """
    Должностные инструкции - просмотр
    """

    model = DocumentsJobDescription
    permission_required = "hrdepartment_app.view_documentsjobdescription"

    def dispatch(self, request, *args, **kwargs):
        try:
            if request.user.is_anonymous:
                return redirect(reverse('customers_app:login'))
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(
                pk=self.request.user.pk
            ).user_access.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy("library_app:documents_list")
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy("library_app:documents_list")
            return redirect(url_match)
        return super(DocumentsJobDescriptionDetail, self).dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class DocumentsJobDescriptionUpdate(
    PermissionRequiredMixin, LoginRequiredMixin, UpdateView
):
    """
    Должностные инструкции - редактирование
    """

    template_name = "hrdepartment_app/documentsjobdescription_update.html"
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionUpdateForm
    permission_required = "hrdepartment_app.change_documentsjobdescription"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def form_valid(self, form):
        if form.is_valid():
            refresh_form = form.save(commit=False)
            if refresh_form.parent_document:
                refresh_form.previous_document = reverse('hrdepartment_app:jobdescription_update',
                                                         args=[refresh_form.parent_document.pk])
            refresh_form.save()
        return super().form_valid(form)

    # def get_form_kwargs(self):
    #     """
    #     Передаем в форму текущего пользователя. В форме переопределяем метод __init__
    #     :return: PK текущего пользователя
    #     """
    #     kwargs = super().get_form_kwargs()
    #     kwargs.update({"user": self.request.user.pk})
    #     return kwargs


# Приказы
class DocumentsOrderList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Список приказов
    """

    model = DocumentsOrder
    permission_required = "hrdepartment_app.view_documentsorder"

    # def get_queryset(self):
    #     qs = super().get_queryset().filter(allowed_placed=True)
    #     print(qs)
    #     return DocumentsOrder.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        # cancellation = request.GET.get("cancellation", None)
        # if request.headers.get("x-requested-with") == "XMLHttpRequest":
        #     if cancellation == "true":
        #         documents_order_list = (
        #             DocumentsOrder.objects.all()
        #         )
        #     else:
        #         documents_order_list = (
        #             DocumentsOrder.objects.filter(
        #                 Q(cancellation=False) & Q(validity_period_end__gte=datetime.datetime.now()))
        #         )
        #
        #     data = [
        #         documents_order_item.get_data()
        #         for documents_order_item in documents_order_list
        #     ]
        #     response = {"data": data}
        #     return JsonResponse(response)
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['document_number', 'document_date',
                           'document_name__name', 'document_foundation__person__title', 'validity_period_end',
                           ]
            context = ajax_search(request, self, search_list, DocumentsOrder, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Приказы"
        return context


class DocumentsOrderAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Добавление приказа
    """

    model = DocumentsOrder
    form_class = DocumentsOrderAddForm
    permission_required = "hrdepartment_app.add_documentsorder"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавление приказа"
        return context

    def get(self, request, *args, **kwargs):
        document_foundation = request.GET.get("document_foundation", None)
        if document_foundation:
            memo_obj = OfficialMemo.objects.get(pk=document_foundation)
            dict_obj = {
                "period_from": datetime.datetime.strftime(
                    memo_obj.period_from, "%Y-%m-%d"
                ),
                "period_for": datetime.datetime.strftime(
                    memo_obj.period_for, "%Y-%m-%d"
                ),
                "document_date": datetime.datetime.strftime(
                    datetime.datetime.today(), "%Y-%m-%d"
                ),
            }
            return JsonResponse(dict_obj, safe=False)
        document_date = request.GET.get("document_date", None)
        if document_date:
            document_date = datetime.datetime.strptime(document_date, "%Y-%m-%d")
            order_list = [
                item.document_number
                for item in DocumentsOrder.objects.filter(document_date=document_date)
                .exclude(cancellation=True)
            ]
            cancel_order = [
                item.document_number
                for item in DocumentsOrder.objects.filter(
                    Q(document_date=document_date) & Q(cancellation=True)
                )
            ]
            if len(order_list) > 0:
                if len(cancel_order) > 0:
                    result = (
                            "Крайний: "
                            + str(order_list[-1])
                            + "; Отмененные: "
                            + "; ".join(cancel_order)
                    )
                else:
                    result = "Крайний: " + str(order_list[-1])
            else:
                result = "За этот день нет приказов."
            dict_obj = {"document_date": result}
            return JsonResponse(dict_obj, safe=False)

        return super().get(request, *args, **kwargs)


class DocumentsOrderDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    # Приказ - просмотр
    model = DocumentsOrder
    permission_required = "hrdepartment_app.view_documentsorder"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        try:
            if request.user.is_anonymous:
                return redirect(reverse('customers_app:login'))
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = self.get_object()
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
            # Сравниваем права доступа
            if detail_obj.access.level < user_obj.user_access.level:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy("hrdepartment_app:order_list")
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy("hrdepartment_app:order_list")
            return redirect(url_match)

        return response

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class DocumentsOrderUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    # Приказ - изменение
    template_name = "hrdepartment_app/documentsorder_update.html"
    model = DocumentsOrder
    form_class = DocumentsOrderUpdateForm
    permission_required = "hrdepartment_app.change_documentsorder"

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        obj_item = self.get_object()
        kwargs = super().get_form_kwargs()
        kwargs.update({"id": obj_item.pk})
        return kwargs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def get(self, request, *args, **kwargs):
        document_foundation = request.GET.get("document_foundation", None)
        if document_foundation:
            memo_obj = OfficialMemo.objects.get(pk=document_foundation)
            dict_obj = {
                "period_from": datetime.datetime.strftime(
                    memo_obj.period_from, "%Y-%m-%d"
                ),
                "period_for": datetime.datetime.strftime(
                    memo_obj.period_for, "%Y-%m-%d"
                ),
                "document_date": datetime.datetime.strftime(
                    datetime.datetime.today(), "%Y-%m-%d"
                ),
            }

            return JsonResponse(dict_obj, safe=False)
        document_date = request.GET.get("document_date", None)
        if document_date:
            document_date = datetime.datetime.strptime(document_date, "%Y-%m-%d")
            order_list = [
                item.document_number
                for item in DocumentsOrder.objects.filter(document_date=document_date)
                .order_by("document_date")
                .exclude(cancellation=True)
            ]
            cancel_order = [
                item.document_number
                for item in DocumentsOrder.objects.filter(
                    Q(document_date=document_date) & Q(cancellation=True)
                ).order_by("document_date")
            ]
            if len(order_list) > 0:
                if len(cancel_order) > 0:
                    result = (
                            "Крайний: "
                            + str(order_list[-1])
                            + "; Отмененные: "
                            + "; ".join(cancel_order)
                    )
                else:
                    result = "Крайний: " + str(order_list[-1])
            else:
                result = "За этот день нет приказов."
            dict_obj = {"document_date": result}
            return JsonResponse(dict_obj, safe=False)
        return super().get(request, *args, **kwargs)


class PlaceProductionActivityList(
    PermissionRequiredMixin, LoginRequiredMixin, ListView
):
    # Места назначения - список
    model = PlaceProductionActivity
    permission_required = "hrdepartment_app.view_placeproductionactivity"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            place_list = PlaceProductionActivity.objects.all()
            data = [place_item.get_data() for place_item in place_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Места назначения"
        return context


class PlaceProductionActivityAdd(
    PermissionRequiredMixin, LoginRequiredMixin, CreateView
):
    # Места назначения - создание
    model = PlaceProductionActivity
    form_class = PlaceProductionActivityAddForm
    permission_required = "hrdepartment_app.add_placeproductionactivity"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить место назначения"
        return context


class PlaceProductionActivityDetail(
    PermissionRequiredMixin, LoginRequiredMixin, DetailView
):
    # Места назначения - просмотр
    model = PlaceProductionActivity
    permission_required = "hrdepartment_app.view_placeproductionactivity"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class PlaceProductionActivityUpdate(
    PermissionRequiredMixin, LoginRequiredMixin, UpdateView
):
    # Места назначения - изменение
    model = PlaceProductionActivity
    template_name = "hrdepartment_app/placeproductionactivity_form_update.html"
    form_class = PlaceProductionActivityUpdateForm
    permission_required = "hrdepartment_app.change_placeproductionactivity"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context


class ReportCardList(LoginRequiredMixin, ListView):
    model = ReportCard

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get("report_month")
        current_year = self.request.GET.get("report_year")
        if current_month and current_year:
            request.session["current_month"] = int(current_month)
            request.session["current_year"] = int(current_year)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session["current_month"] and request.session["current_year"]:
                start_date = datetime.date(
                    year=int(request.session["current_year"]),
                    month=int(request.session["current_month"]),
                    day=1,
                )
                end_date = start_date + relativedelta(days=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                reportcard_list = (
                    ReportCard.objects.filter(
                        Q(employee=self.request.user)
                        & Q(record_type="13")
                        & Q(report_card_day__in=search_interval)
                    )
                    .order_by("report_card_day")
                    .reverse()
                )
            else:
                reportcard_list = (
                    ReportCard.objects.filter(
                        Q(employee=self.request.user) & Q(record_type="13")
                    )
                    .order_by("report_card_day")
                    .reverse()
                )
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["current_year"] = self.request.session["current_year"]
        context["current_month"] = str(self.request.session["current_month"])
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком"
        return context


class ReportCardListManual(LoginRequiredMixin, ListView):
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_list_manual.html"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get("report_month")
        current_year = self.request.GET.get("report_year")
        if current_month and current_year:
            request.session["current_month"] = int(current_month)
            request.session["current_year"] = int(current_year)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session["current_month"] and request.session["current_year"]:
                start_date = datetime.date(
                    year=int(request.session["current_year"]),
                    month=int(request.session["current_month"]),
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                reportcard_list = (
                    ReportCard.objects.filter(
                        Q(record_type="13") & Q(report_card_day__in=search_interval)
                    )
                    .order_by("report_card_day")
                    .reverse()
                )
            else:
                start_date = datetime.date(
                    year=datetime.datetime.today().year,
                    month=datetime.datetime.today().month,
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                reportcard_list = (
                    ReportCard.objects.filter(
                        Q(record_type="13") & Q(report_card_day__in=search_interval)
                    )
                    .order_by("report_card_day")
                    .reverse()
                )
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["current_year"] = self.request.session["current_year"]
        context["current_month"] = str(self.request.session["current_month"])
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком"
        return context


class ReportCardListAdmin(LoginRequiredMixin, ListView):
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_list_admin.html"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get("report_month")
        current_year = self.request.GET.get("report_year")
        if current_month and current_year:
            request.session["current_month"] = int(current_month)
            request.session["current_year"] = int(current_year)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            query = Q()
            if request.session["current_month"] and request.session["current_year"]:
                start_date = datetime.date(
                    year=int(request.session["current_year"]),
                    month=int(request.session["current_month"]),
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                query &= Q(report_card_day__in=search_interval)
            else:
                start_date = datetime.date(
                    year=datetime.datetime.today().year,
                    month=datetime.datetime.today().month,
                    day=1,
                )
                end_date = start_date + relativedelta(day=31)
                search_interval = list(
                    rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date)
                )
                query &= Q(report_card_day__in=search_interval)

            search_list = ['report_card_day', 'employee__title',
                           'start_time', 'end_time', 'reason_adjustment', 'record_type']
            context = ajax_search(request, self, search_list, ReportCard, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["current_year"] = self.request.session["current_year"]
        context["current_month"] = str(self.request.session["current_month"])
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком"
        return context


class ReportCardDelete(LoginRequiredMixin, DeleteView):
    model = ReportCard
    success_url = "/hr/report/admin/"


class ReportCardDetailYearXLS(View):
    def get(self, request, *args, **kwargs):
        df = get_year_report(html_mode=False)
        # Создание Excel-файла
        response = HttpResponse(content_type='application/ms-excel')
        response['Content-Disposition'] = 'attachment; filename="dataframe.xlsx"'

        # Запись DataFrame в Excel
        df.to_excel(response, index=True, engine='openpyxl')

        return response


class ReportCardDetailYear(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_detail_year.html"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context["table"] = get_year_report()
        print(context["table"])
        return context


class ReportCardDetailFact(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_detail_fact.html"

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse("hrdepartment_app:reportcard_detail"))

    def get_queryset(self):
        queryset = ReportCard.objects.all()
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.request.GET.get("report_month", None)
        year = self.request.GET.get("report_year", None)

        if month and year:
            current_day = datetime.datetime(int(year), int(month), 1)
        else:
            current_day = datetime.datetime.today() + relativedelta(day=1)

        first_day = current_day + relativedelta(day=1)
        last_day = current_day + relativedelta(day=31)
        # Выбираем пользователей, кто отмечался в течении интервала
        report_obj_list = (
            ReportCard.objects.filter(
                Q(report_card_day__gte=first_day)
                & Q(record_type__in=["1", "13"])
                & Q(report_card_day__lte=last_day)
            )
            .values("employee")
            .order_by("employee__last_name")
        )
        users_obj_list = []
        for item in report_obj_list:
            if item["employee"] not in users_obj_list:
                users_obj_list.append(item["employee"])
        users_obj_set = dict()
        for item in users_obj_list:
            users_obj_set[item] = DataBaseUser.objects.get(pk=item)

        month_obj = get_month(current_day)
        all_dict = dict()
        norm_time = ProductionCalendar.objects.get(calendar_month=current_day)
        # Итерируемся по списку сотрудников
        for user_obj in users_obj_set:
            (
                data_dict,
                total_score,
                all_days_count,
                all_vacation_days,
                all_vacation_time,
                holiday_delta,
            ) = get_working_hours(user_obj, current_day, state=2)
            absences = all_days_count - (
                    norm_time.number_working_days - all_vacation_days
            )
            absences_delta = (
                    norm_time.get_norm_time() - (all_vacation_time + total_score) / 3600
            )
            if absences_delta < 0:
                hour1, minute1 = divmod(total_score / 60, 60)
                time_count_hour = "{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм".format(
                    hour1, minute1
                )
            else:
                hour1, minute1 = divmod(total_score / 60, 60)
                hour2, minute2 = divmod(absences_delta * 60, 60)
                time_count_hour = "{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм<br>-{2:3.0f}&nbspч&nbsp{3:2.0f}&nbspм".format(
                    hour1, minute1, hour2, minute2
                )
            all_dict[users_obj_set[user_obj]] = {
                "dict_count": data_dict,
                "days_count": all_days_count,  # days_count,
                "time_count_day": datetime.timedelta(seconds=total_score).days,
                # time_count.days, # Итого отмечено часов за месяц # Итого отмечено дней за месяц
                "time_count_hour": time_count_hour,
                # (time_count.total_seconds() / 3600),# Итого отмечено часов за месяц
                "absences": abs(absences) if absences < 0 else 0,  # Количество неявок
                "vacation_time": (all_vacation_time + total_score) / 3600,
                "holidays": norm_time.number_days_off_and_holidays - holiday_delta,
            }
        month_dict, year_dict = get_year_interval(2020)
        context["range"] = [item for item in range(1, 17)]
        context["range2"] = [item for item in range(16, 32)]
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["all_dict"] = all_dict
        context["month_obj"] = month_obj
        context["first_day"] = first_day
        context["norm_time"] = norm_time.get_norm_time()
        context["norm_day"] = norm_time.number_working_days
        context["holidays"] = norm_time.number_days_off_and_holidays
        context["last_day"] = last_day
        context["current_year"] = datetime.datetime.today().year
        context["current_month"] = str(datetime.datetime.today().month)
        context["tabel_month"] = first_day
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени (факт)"
        return context


class ReportCardDetailIAS(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_detail_ias.html"

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse("hrdepartment_app:reportcard_detail"))

    def get_queryset(self):
        queryset = ReportCard.objects.all()
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.request.GET.get("report_month", None)
        year = self.request.GET.get("report_year", None)

        if month and year:
            current_day = datetime.datetime(int(year), int(month), 1)
        else:
            current_day = datetime.datetime.today() + relativedelta(day=1)

        first_day = current_day + relativedelta(day=1)
        last_day = current_day + relativedelta(day=31)
        # Выбираем пользователей, кто отмечался в течении интервала
        report_obj_list = (
            ReportCard.objects.filter(
                Q(report_card_day__gte=first_day)
                & Q(sign_report_card=True)
                & Q(report_card_day__lte=last_day)
            )
            .values("employee")
            .order_by("employee__last_name")
        )
        users_obj_list = []
        for item in report_obj_list:
            if item["employee"] not in users_obj_list:
                users_obj_list.append(item["employee"])
        users_obj_set = dict()
        for item in users_obj_list:
            users_obj_set[item] = DataBaseUser.objects.get(pk=item)

        month_obj = get_month(current_day)
        all_dict = dict()
        norm_time = ProductionCalendar.objects.get(calendar_month=current_day)
        # Итерируемся по списку сотрудников

        month_dict, year_dict = get_year_interval(2020)
        context["range"] = [item for item in range(1, 17)]
        context["range2"] = [item for item in range(16, 32)]
        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["month_obj"] = month_obj
        context["first_day"] = first_day
        context["norm_time"] = norm_time.get_norm_time()
        context["norm_day"] = norm_time.number_working_days
        context["holidays"] = norm_time.number_days_off_and_holidays
        context["last_day"] = last_day
        context["current_year"] = datetime.datetime.today().year
        context["current_month"] = str(datetime.datetime.today().month)
        context["tabel_month"] = first_day
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени (факт)"
        return context


class ReportCardDetail(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = "hrdepartment_app/reportcard_detail.html"

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse("hrdepartment_app:reportcard_detail"))

    def get_queryset(self):
        queryset = ReportCard.objects.all()
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.request.GET.get("report_month", None)
        year = self.request.GET.get("report_year", None)

        if month and year:
            current_day = datetime.datetime(int(year), int(month), 1)
        else:
            current_day = datetime.datetime.today() + relativedelta(day=1)

        first_day = current_day + relativedelta(day=1)
        last_day = current_day + relativedelta(day=31)
        # Выбираем пользователей, кто отмечался в течении интервала
        report_obj_list = (
            ReportCard.objects.filter(
                Q(report_card_day__gte=first_day)
                & Q(record_type__in=["1", "13"])
                & Q(report_card_day__lte=last_day)
            )
            .values("employee")
            .order_by("employee__last_name")
        )
        users_obj_list = []
        for item in report_obj_list:
            if item["employee"] not in users_obj_list:
                users_obj_list.append(item["employee"])
        users_obj_set = dict()
        for item in users_obj_list:
            users_obj_set[item] = DataBaseUser.objects.get(pk=item)

        month_obj = get_month(current_day)
        all_dict = dict()
        norm_time = ProductionCalendar.objects.get(calendar_month=current_day)
        # Итерируемся по списку сотрудников
        for user_obj in users_obj_set:
            (
                data_dict,
                total_score,
                all_days_count,
                all_vacation_days,
                all_vacation_time,
                holiday_delta,
            ) = get_working_hours(user_obj, current_day, state=1)
            absences = all_days_count - (
                    norm_time.number_working_days - all_vacation_days
            )
            absences_delta = (
                    norm_time.get_norm_time() - (all_vacation_time + total_score) / 3600
            )
            if absences_delta < 0:
                hour1, minute1 = divmod(total_score / 60, 60)
                time_count_hour = "{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм".format(
                    hour1, minute1
                )
            else:
                hour1, minute1 = divmod(total_score / 60, 60)
                hour2, minute2 = divmod(absences_delta * 60, 60)
                time_count_hour = "{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм<br>-{2:3.0f}&nbspч&nbsp{3:2.0f}&nbspм".format(
                    hour1, minute1, hour2, minute2
                )
            all_dict[users_obj_set[user_obj]] = {
                "dict_count": data_dict,
                "days_count": all_days_count,  # days_count,
                "time_count_day": datetime.timedelta(seconds=total_score).days,
                # time_count.days, # Итого отмечено часов за месяц # Итого отмечено дней за месяц
                "time_count_hour": time_count_hour,
                # (time_count.total_seconds() / 3600),# Итого отмечено часов за месяц
                "absences": abs(absences) if absences < 0 else 0,  # Количество неявок
                "vacation_time": (all_vacation_time + total_score) / 3600,
                "holidays": norm_time.number_days_off_and_holidays - holiday_delta,
            }
        month_dict, year_dict = get_year_interval(2020)

        context["year_dict"] = year_dict
        context["month_dict"] = month_dict
        context["all_dict"] = all_dict
        context["month_obj"] = month_obj
        context["first_day"] = first_day
        context["norm_time"] = norm_time.get_norm_time()
        context["norm_day"] = norm_time.number_working_days
        context["holidays"] = norm_time.number_days_off_and_holidays
        context["last_day"] = last_day
        context["current_year"] = datetime.datetime.today().year
        context["current_month"] = str(datetime.datetime.today().month)
        context["tabel_month"] = first_day
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени"
        return context


class ReportCardAdd(LoginRequiredMixin, CreateView):
    model = ReportCard
    form_class = ReportCardAddForm

    def get(self, request, *args, **kwargs):
        interval = request.GET.get("interval", None)
        if interval:
            personal_start = (
                self.request.user.user_work_profile.personal_work_schedule_start
            )
            personal_start = datetime.timedelta(
                hours=personal_start.hour, minutes=personal_start.minute
            ) - datetime.timedelta(hours=3)
            personal_end = (
                self.request.user.user_work_profile.personal_work_schedule_end
            )

            if datetime.datetime.strptime(interval, "%Y-%m-%d").weekday() == 4:
                personal_end = datetime.timedelta(
                    hours=personal_end.hour, minutes=personal_end.minute
                )
            else:
                personal_end = datetime.timedelta(
                    hours=personal_end.hour, minutes=personal_end.minute
                ) + datetime.timedelta(hours=2)
            result = [
                datetime.datetime.strptime(str(personal_start), "%H:%M:%S")
                .time()
                .strftime("%H:%M"),
                datetime.datetime.strptime(str(personal_end), "%H:%M:%S")
                .time()
                .strftime("%H:%M"),
            ]
            return JsonResponse(result, safe=False)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            search_report = ReportCard.objects.filter(
                Q(employee=self.request.user)
                & Q(report_card_day=form.cleaned_data.get("report_card_day"))
                & Q(record_type="1")
            )
            dt = form.cleaned_data.get("report_card_day")
            search_interval = list()
            start_time = list()
            end_time = list()
            for item in search_report:
                start_time.append(item.start_time.strftime("%H:%M"))
                end_time.append(item.end_time.strftime("%H:%M"))
                first_date1 = datetime.datetime(
                    year=dt.year,
                    month=dt.month,
                    day=dt.day,
                    hour=item.start_time.hour,
                    minute=item.start_time.minute,
                )
                first_date2 = datetime.datetime(
                    year=dt.year,
                    month=dt.month,
                    day=dt.day,
                    hour=item.end_time.hour,
                    minute=item.end_time.minute,
                )
                search_interval = list(
                    rrule.rrule(rrule.MINUTELY, dtstart=first_date1, until=first_date2)
                )
            first_date3 = datetime.datetime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=form.cleaned_data.get("start_time").hour,
                minute=form.cleaned_data.get("start_time").minute,
            )
            first_date4 = datetime.datetime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=form.cleaned_data.get("end_time").hour,
                minute=form.cleaned_data.get("end_time").minute,
            )
            interval = list(
                rrule.rrule(rrule.MINUTELY, dtstart=first_date3, until=first_date4)
            )
            set1 = set(search_interval)
            set2 = set(interval)
            result = set2.intersection(set1)
            if len(result) > 0:
                form.add_error(
                    "start_time",
                    f'Ошибка! Вы указали время с {form.cleaned_data.get("start_time").strftime("%H:%M")} по {form.cleaned_data.get("end_time").strftime("%H:%M")}, но на заданную дату По TimeControl у вас имеется интервал с {start_time} по {end_time}',
                )
                return super().form_invalid(form)

            refresh_form = form.save(commit=False)
            refresh_form.employee = self.request.user
            refresh_form.record_type = "13"
            refresh_form.manual_input = True

            refresh_form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("customers_app:profile", args=(self.request.user.pk,))


class ReportCardUpdate(LoginRequiredMixin, UpdateView):
    model = ReportCard
    form_class = ReportCardUpdateForm
    template_name = "hrdepartment_app/reportcard_form_update.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_obj = self.get_object()
        if self.request.user.is_superuser:
            context["min"] = datetime.datetime(1, 1, 1, 1, 0).strftime("%H:%M")
            context["max"] = datetime.datetime(1, 1, 1, 23, 0).strftime("%H:%M")
        else:
            context[
                "min"
            ] = user_obj.employee.user_work_profile.personal_work_schedule_start.strftime(
                "%H:%M"
            )
            context[
                "max"
            ] = user_obj.employee.user_work_profile.personal_work_schedule_end.strftime(
                "%H:%M"
            )
        return context

    def get(self, request, *args, **kwargs):
        interval = request.GET.get("interval", None)
        if interval:
            personal_start = (
                self.request.user.user_work_profile.personal_work_schedule_start
            )
            personal_start = datetime.timedelta(
                hours=personal_start.hour, minutes=personal_start.minute
            ) - datetime.timedelta(hours=3)
            personal_end = (
                self.request.user.user_work_profile.personal_work_schedule_end
            )

            if datetime.datetime.strptime(interval, "%Y-%m-%d").weekday() == 4:
                personal_end = datetime.timedelta(
                    hours=personal_end.hour, minutes=personal_end.minute
                )
            else:
                personal_end = datetime.timedelta(
                    hours=personal_end.hour, minutes=personal_end.minute
                ) + datetime.timedelta(hours=2)
            result = [
                datetime.datetime.strptime(str(personal_start), "%H:%M:%S")
                .time()
                .strftime("%H:%M"),
                datetime.datetime.strptime(str(personal_end), "%H:%M:%S")
                .time()
                .strftime("%H:%M"),
            ]
            return JsonResponse(result, safe=False)
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("hrdepartment_app:reportcard_list")

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


# Положения
class ProvisionsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Должностные инструкции - список
    """

    model = Provisions
    permission_required = "hrdepartment_app.view_provisions"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            provisions_list = Provisions.objects.all()
            data = [provisions_item.get_data() for provisions_item in provisions_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Положения"
        return context


class ProvisionsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Положения - создание
    """

    model = Provisions
    form_class = ProvisionsAddForm
    permission_required = "hrdepartment_app.add_provisions"

    def get_context_data(self, **kwargs):
        content = super(ProvisionsAdd, self).get_context_data(**kwargs)
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить положение"
        return content

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


class ProvisionsDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Положения - просмотр
    """

    model = Provisions
    permission_required = "hrdepartment_app.view_provisions"

    def dispatch(self, request, *args, **kwargs):
        try:
            if request.user.is_anonymous:
                return redirect(reverse('customers_app:login'))
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(
                pk=self.request.user.pk
            ).user_access.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy("hrdepartment_app:provisions_list")
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy("hrdepartment_app:provisions_list")
            return redirect(url_match)
        return super(ProvisionsDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class ProvisionsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    """
    Положения - редактирование
    """

    template_name = "hrdepartment_app/provisions_form_update.html"
    model = Provisions
    form_class = ProvisionsUpdateForm
    permission_required = "hrdepartment_app.change_provisions"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


# Руководящие документы
class GuidanceDocumentsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Руководящие документы - список
    """

    model = GuidanceDocuments
    permission_required = "hrdepartment_app.view_guidancedocuments"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            provisions_list = GuidanceDocuments.objects.all()
            data = [provisions_item.get_data() for provisions_item in provisions_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Руководящие документы"
        return context


class GuidanceDocumentsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Руководящие документы - создание
    """

    model = GuidanceDocuments
    form_class = GuidanceDocumentsAddForm
    permission_required = "hrdepartment_app.add_guidancedocuments"

    def get_context_data(self, **kwargs):
        content = super(GuidanceDocumentsAdd, self).get_context_data(**kwargs)
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить руководящий документ"
        return content

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


class GuidanceDocumentsDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Руководящий документ - просмотр
    """

    model = GuidanceDocuments
    permission_required = "hrdepartment_app.view_guidancedocuments"

    def dispatch(self, request, *args, **kwargs):
        try:
            if request.user.is_anonymous:
                return redirect(reverse('customers_app:login'))
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(
                pk=self.request.user.pk
            ).user_access.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy("hrdepartment_app:guidance_documents_list")
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy("hrdepartment_app:guidance_documents_list")
            return redirect(url_match)
        return super(GuidanceDocumentsDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        return context


class GuidanceDocumentsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    """
    Руководящий документ - редактирование
    """

    template_name = "hrdepartment_app/guidancedocuments_form_update.html"
    model = GuidanceDocuments
    form_class = GuidanceDocumentsUpdateForm
    permission_required = "hrdepartment_app.change_guidancedocuments"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs


# Приказы о старших бригад
class CreatingTeamList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Приказы о старших бригад - список
    """

    model = CreatingTeam
    permission_required = "hrdepartment_app.view_creatingteam"
    paginate_by = 10
    ordering = "-id"

    def get(self, request, *args, **kwargs):
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['senior_brigade__title', 'date_start',
                           'date_end', 'number', 'date_create',
                           'place__name', 'agreed', 'cancellation',
                           'executor_person__title', "email_send",
                           ]
            context = ajax_search(request, self, search_list, CreatingTeam, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Приказы о старших бригад"
        return context


class CreatingTeamAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Приказы о старших бригад - создание
    """

    model = CreatingTeam
    form_class = CreatingTeamAddForm
    permission_required = "hrdepartment_app.add_creatingteam"

    def get_context_data(self, **kwargs):
        content = super(CreatingTeamAdd, self).get_context_data(**kwargs)
        content[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить приказ о старших бригад"

        return content

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        document_type = request.GET.get("document_type", None)
        if document_type:
            html = {"replaceable_document": ""}
            if document_type == "1":
                check_data = datetime.datetime.today() + relativedelta(months=-2)
                team_list = CreatingTeam.objects.filter(
                    Q(date_end__gte=check_data) &
                    Q(agreed=True) &
                    Q(cancellation=False)
                ).exclude(number='')
                team_list_obj = dict()
                for item in team_list:
                    team_list_obj.update({str(item): item.pk})
                html["replaceable_document"] = team_list_obj
                print(html)
                return JsonResponse(html)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        refreshed_form = form.save(commit=False)
        if refreshed_form.replaceable_document:
            replaceable_document = refreshed_form.replaceable_document

            current_context = {
                "name": replaceable_document.senior_brigade.first_name,
                "surname": replaceable_document.senior_brigade.surname,
                "text": f'Приказ № {replaceable_document.number} от {replaceable_document.date_create.strftime("%d.%m.%Y")} отменен.',
                "sign": f'Исполнитель {format_name_initials(replaceable_document.executor_person)}'}
            attachment_path = ''
            subject = f"Отмена приказа № {replaceable_document.number} о назначении старшего бригады"
            sm = send_notification(replaceable_document.executor_person, replaceable_document, subject,
                                   "hrdepartment_app/creatingteam_email.html", current_context,
                                   attachment=attachment_path, division=1, document=1)
            if sm == 1:
                replaceable_document.cancellation = True
                replaceable_document.save()
            else:
                self.form_invalid(form)
        refreshed_form.save()

        notify_dict = {
            'name': 'team_create_approve',
            'document_type': 'CTO',
            'division_type': '2'
        }
        get_notify(CreatingTeam, Q(agreed=False), Notification, notify_dict, BusinessProcessDirection,
                   Q(business_process_type='2'), "person_agreement")
        return super().form_valid(form)


class CreatingTeamDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Приказы о старших бригад - просмотр
    """
    model = CreatingTeam
    permission_required = "hrdepartment_app.view_creatingteam"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}"
        user_job = self.request.user.user_work_profile.job.pk
        persons_list = BusinessProcessDirection.objects.filter(business_process_type="2")
        for person in persons_list:
            if user_job in [item.pk for item in person.person_executor.iterator()]:
                context["is_executor"] = True
            if user_job in [item.pk for item in person.person_agreement.iterator()]:
                context["is_agreement"] = True
            if user_job in [item.pk for item in person.person_hr.iterator()]:
                context["is_hr"] = True
            if user_job in [item.pk for item in person.clerk.iterator()]:
                context["is_clerk"] = True
        if not self.object.email_send and self.object.scan_file:
            context["email_send"] = True
        context["change_history"] = get_history(self, CreatingTeam)
        return context

    def get(self, request, *args, **kwargs):
        get_object = self.get_object()
        kwargs = {
            "template_name": "hrdepartment_app/creatingteam_email.html",
            "sender": EMAIL_HOST_USER,
            "receiver": [get_object.senior_brigade.email, get_object.place.email, ],
            "attachment_path": get_object.scan_file.url if get_object.scan_file else None,
            "current_context": {
                "name": get_object.senior_brigade.first_name,
                "surname": get_object.senior_brigade.surname,
                "text": f'Вы назначены старшим бригадой в {get_object.place.name} с {get_object.date_start.strftime("%d.%m.%Y")} по {get_object.date_end.strftime("%d.%m.%Y")}.',
                "sign": f'Исполнитель {format_name_initials(get_object.executor_person)}'}
        }
        if request.GET.get('sm') == '1':
            kwargs["subject"] = "Назначение старшего бригады"
            current_context = {
                "name": get_object.senior_brigade.first_name,
                "surname": get_object.senior_brigade.surname,
                "text": f'Вы назначены старшим бригадой в {get_object.place.name} с {get_object.date_start.strftime("%d.%m.%Y")} по {get_object.date_end.strftime("%d.%m.%Y")}.',
                "sign": f'Исполнитель {format_name_initials(get_object.executor_person)}'}
            attachment_path = get_object.scan_file.url if get_object.scan_file else ''
            sm = send_notification(get_object.executor_person, get_object, 'Назначение старшего бригады',
                                   "hrdepartment_app/creatingteam_email.html", current_context,
                                   attachment=attachment_path, division=1, document=1)
            if sm == 1:
                get_object.email_send = True
                get_object.save()
                notify_dict = {
                    'name': 'team_check_clerk',
                    'document_type': 'CTO',
                    'division_type': '2'
                }
                query = Q(agreed=True) & ~Q(number='') & ~Q(scan_file='')
                get_notify(CreatingTeam, query, Notification, notify_dict, BusinessProcessDirection,
                           Q(business_process_type='2'), "person_hr")

        if request.GET.get('sm') == '2':
            kwargs["subject"] = "Повторное уведомление о назначение старшего бригады"
            if send_mail_notification(kwargs, get_object, 0):
                get_object.email_send = True
                get_object.save()

        return super().get(request, *args, **kwargs)


class CreatingTeamUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    """
    Приказы о старших бригад - редактирование
    """

    template_name = "hrdepartment_app/creatingteam_form_update.html"
    model = CreatingTeam
    form_class = CreatingTeamUpdateForm
    permission_required = "hrdepartment_app.change_creatingteam"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        return kwargs

    def form_valid(self, form):
        if form.is_valid():
            if form.changed_data:
                old_dict = {}
                get_object = self.get_object()
                for item in form.changed_data:
                    if item in ["team_brigade", "company_property"]:
                        old_dict[item] = [item for item in getattr(get_object, item).all()]
                    else:
                        old_dict[item] = getattr(get_object, item)
                refresh_form = form.save(commit=False)
                refresh_form.scan_file = None
                refresh_form.email_send = False
                refresh_form.save()
                form.save_m2m()
                get_object = self.get_object()
                new_dict = {}
                for item in form.changed_data:
                    if item in ["team_brigade", "company_property"]:
                        new_dict[item] = [item for item in getattr(get_object, item).all()]
                    else:
                        new_dict[item] = getattr(get_object, item)
                notify_dict = {
                    'name': 'team_check_clerk',
                    'document_type': 'CTO',
                    'division_type': '2'
                }
                query = Q(agreed=True) & ~Q(number='') & ~Q(scan_file='')
                get_notify(CreatingTeam, query, Notification, notify_dict, BusinessProcessDirection,
                           Q(business_process_type='2'), "clerk")

                message = ("<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:<br>")

                for k in form.changed_data:
                    if old_dict[k] != new_dict[k]:
                        message += f"{self.object._meta.get_field(k).verbose_name}: <strike>{old_dict[k]}</strike> -> {new_dict[k]}<br>"
                self.object.history_change.create(author=self.request.user, body=message)
        return super().form_valid(form)


class CreatingTeamDelete(PermissionRequiredMixin, LoginRequiredMixin, DeleteView):  # DeleteView
    model = CreatingTeam  # Приказы о старших бригад - удаление
    template_name = "hrdepartment_app/creatingteam_confirm_delete.html"
    success_url = reverse_lazy("hrdepartment_app:creatingteam_list")
    permission_required = "hrdepartment_app.delete_creatingteam"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Удаление - {self.get_object()}"
        return context


class CreatingTeamAgreed(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):  # UpdateView
    model = CreatingTeam
    template_name = "hrdepartment_app/creatingteam_form_agreed.html"
    form_class = CreatingTeamAgreedForm
    permission_required = "hrdepartment_app.change_creatingteam"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Согласование - {self.get_object()}"
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        approving_job_list = [item['person_agreement'] for item in
                              BusinessProcessDirection.objects.filter(business_process_type=2).values(
                                  'person_agreement')]
        approving_person_list = [item.pk for item in DataBaseUser.objects.filter(
            user_work_profile__job__in=approving_job_list).exclude(is_active=False)]
        kwargs.update({"approving_person": approving_person_list})
        return kwargs

    def form_valid(self, form):
        if form.is_valid():
            form.save()
            notify_dict = {
                'name': 'team_create_approve',
                'document_type': 'CTO',
                'division_type': '2'
            }
            get_notify(CreatingTeam, Q(agreed=False), Notification, notify_dict, BusinessProcessDirection,
                       Q(business_process_type='2'), "person_agreement")
            notify_dict = {
                'name': 'team_check_hr',
                'document_type': 'CTO',
                'division_type': '2'
            }
            query = Q(agreed=True) & (Q(number='') | Q(scan_file=''))
            get_notify(CreatingTeam, query, Notification, notify_dict, BusinessProcessDirection,
                       Q(business_process_type='2'), "person_hr")
        return super().form_valid(form)


class CreatingTeamSetNumber(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):  # UpdateView
    model = CreatingTeam
    template_name = "hrdepartment_app/creatingteam_form_number.html"
    form_class = CreatingTeamSetNumberForm
    permission_required = "hrdepartment_app.change_creatingteam"
    success_url = reverse_lazy("hrdepartment_app:team_list")

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Присвоение номера - {self.get_object()}"
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user.pk})
        hr_job_list = [item['person_hr'] for item in
                       BusinessProcessDirection.objects.filter(business_process_type=2).values(
                           'person_hr')]
        hr_person_list = [item.pk for item in DataBaseUser.objects.filter(
            user_work_profile__job__in=hr_job_list).exclude(is_active=False)]
        kwargs.update({"hr_person": hr_person_list})
        return kwargs

    def form_valid(self, form):
        if form.is_valid():
            form.save()

            notify_dict = {
                'name': 'team_check_hr',
                'document_type': 'CTO',
                'division_type': '2'
            }
            query = Q(agreed=True) & (Q(number='') | Q(scan_file=''))
            get_notify(CreatingTeam, query, Notification, notify_dict, BusinessProcessDirection,
                       Q(business_process_type='2'), "person_hr")

            notify_dict = {
                'name': 'team_check_clerk',
                'document_type': 'CTO',
                'division_type': '2'
            }
            query = Q(agreed=True) & ~Q(number='') & ~Q(scan_file='')
            get_notify(CreatingTeam, query, Notification, notify_dict, BusinessProcessDirection,
                       Q(business_process_type='2'), "person_hr")
        return super().form_valid(form)


class ExpensesList(LoginRequiredMixin, ListView):
    model = OfficialMemo
    template_name = "hrdepartment_app/expenses_list.html"

    def get(self, request, *args, **kwargs):
        query = Q()
        expenses_dicts = ApprovalOficialMemoProcess.objects.filter(
            Q(document__expenses=False) &
            Q(document__expenses_summ__gt=0) &
            Q(process_accepted=True)).values('document')
        expenses_list = [item['document'] for item in expenses_dicts]
        query &= Q(id__in=expenses_list)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['type_trip', 'person__title',
                           'person__user_work_profile__job__name', 'place_production_activity__name',
                           'purpose_trip__title',
                           'period_from', 'period_for', 'accommodation',
                           'order__document_number', 'comments', 'period_from',
                           ]
            context = ajax_search(request, self, search_list, OfficialMemo, query)
            return JsonResponse(context, safe=False)
        return super(ExpensesList, self).get(request, *args, **kwargs)


def expenses_update(request, *args, **kwargs):
    obj = OfficialMemo.objects.get(pk=kwargs['pk'])
    obj.expenses = True
    obj.save()
    return redirect("hrdepartment_app:expenses_list")


# class TimeSheetCreateView(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
#     model = TimeSheet
#     form_class = TimeSheetForm  # Используем созданную форму
#     permission_required = "hrdepartment_app.create_timesheet"
#
#     def get_context_data(self, **kwargs):
#         data = super().get_context_data(**kwargs)
#         if self.request.POST:
#             data['report_cards'] = ReportCardFormSet(self.request.POST)
#         else:
#             data['report_cards'] = ReportCardFormSet()
#         return data
#
#     def form_valid(self, form):
#         context = self.get_context_data()
#         report_cards = context['report_cards']
#         for item in report_cards:
#             print(item)
#         self.object = form.save()
#         if report_cards.is_valid():
#             report_cards.instance = self.object
#             report_cards.save()
#         else:
#             print(report_cards.errors)
#         return super().form_valid(form)
#
#     def form_invalid(self, form):
#         print(form.errors)
#         return super().form_invalid(form)

class TimeSheetCreateView(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = TimeSheet
    form_class = TimeSheetForm
    permission_required = "hrdepartment_app.create_timesheet"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['reportcard_formset'] = inlineformset_factory(TimeSheet, ReportCard, form=ReportCardForm, extra=15)(self.request.POST)
        else:
            data['reportcard_formset'] = inlineformset_factory(TimeSheet, ReportCard, form=ReportCardForm, extra=15)()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        reportcard_formset = context['reportcard_formset']
        if reportcard_formset.is_valid():
            self.object = form.save()
            reportcard_formset.instance = self.object
            self.save_formset(reportcard_formset)
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def save_formset(self, formset):
        """
        Переопределение метода save_formset:
            Метод save_formset переопределяется для внесения изменений в поле custom_field модели ReportCard.
            В этом примере поле sign_report_card устанавливается в значение True, но вы можете заменить его на любое
            другое значение или логику.
        Сохранение формсета:
            В методе form_valid после проверки валидности формсета, вызывается метод save_formset для сохранения
            формсета с внесенными изменениями.
        Сохранение связанных объектов:
            Метод save_m2m вызывается для сохранения связанных объектов, если они есть.
        Примечания:
            Убедитесь, что 'поле' существует в модели ReportCard.
            Вы можете изменить логику установки значения поля custom_field в зависимости от ваших требований.
            Этот подход позволяет внести изменения в поле модели, которое не присутствует в форме, но имеется в
            самой модели.
        """
        instances = formset.save(commit=False)
        for instance in instances:
            # Внесите изменения в поле, которое не присутствует в форме
            instance.report_card_day = self.object.date
            instance.sign_report_card = True
            instance.record_type = "13"
            instance.save()
            instance.place_report_card.set([self.object.time_sheets_place.pk, ])
        formset.save_m2m()  # Сохраняем связанные объекты, если есть

    # def get_context_data(self, **kwargs):
    #     data = super().get_context_data(**kwargs)
    #     if self.request.POST:
    #         data['report_cards'] = ReportCardFormSet(self.request.POST, self.request.FILES)
    #     else:
    #         data['report_cards'] = ReportCardFormSet()
    #     return data
    #
    # def form_valid(self, form):
    #     context = self.get_context_data()
    #     report_cards = context['report_cards']
    #     self.object = form.save()
    #     if report_cards.is_valid():
    #         instances = report_cards.save(commit=False)
    #         for instance in instances:
    #             instance.timesheet = self.object
    #             instance.report_card_day = self.object.date
    #             instance.save()
    #     else:
    #         print(report_cards.errors)
    #     return super().form_valid(form)
    # def form_valid(self, form):
    #     context = self.get_context_data()
    #     reportcard_formset = context['report_cards']
    #     self.object = form.save()
    #     if reportcard_formset.is_valid():
    #         self.object = form.save()
    #         reportcard_formset.instance = self.object
    #         reportcard_formset.report_card_day = self.object.date
    #         reportcard_formset.save()
    #         return super().form_valid(form)
    #     else:
    #         return self.form_invalid(form)


class TimeSheetUpdateView(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = TimeSheet
    form_class = TimeSheetForm  # Используем созданную форму
    permission_required = "hrdepartment_app.change_timesheet"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['reportcard_formset'] = inlineformset_factory(TimeSheet, ReportCard, form=ReportCardForm, extra=3)(self.request.POST, instance=self.object)
        else:
            data['reportcard_formset'] = inlineformset_factory(TimeSheet, ReportCard, form=ReportCardForm, extra=3)(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        reportcard_formset = context['reportcard_formset']
        if reportcard_formset.is_valid():
            self.object = form.save()
            reportcard_formset.instance = self.object
            self.save_formset(reportcard_formset)
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def save_formset(self, formset):
        """
        Переопределение метода save_formset:
            Метод save_formset переопределяется для внесения изменений в поле custom_field модели ReportCard.
            В этом примере поле sign_report_card устанавливается в значение True, но вы можете заменить его на любое
            другое значение или логику.
        Сохранение формсета:
            В методе form_valid после проверки валидности формсета, вызывается метод save_formset для сохранения
            формсета с внесенными изменениями.
        Сохранение связанных объектов:
            Метод save_m2m вызывается для сохранения связанных объектов, если они есть.
        Примечания:
            Убедитесь, что 'поле' существует в модели ReportCard.
            Вы можете изменить логику установки значения поля custom_field в зависимости от ваших требований.
            Этот подход позволяет внести изменения в поле модели, которое не присутствует в форме, но имеется в
            самой модели.
        """
        instances = formset.save(commit=False)
        for instance in instances:
            # Внесите изменения в поле, которое не присутствует в форме
            instance.report_card_day = self.object.date
            instance.sign_report_card = True
            instance.place_report_card.set([self.object.time_sheets_place.pk,])
            instance.save()
        formset.save_m2m()  # Сохраняем связанные объекты, если есть

    def form_invalid(self, form):
        return super(TimeSheetUpdateView, self).form_invalid(form)
        




@require_POST
@csrf_exempt
def filter_outfit_cards(request):
    time_sheets_place_id = request.POST.get('time_sheets_place')
    if time_sheets_place_id:
        outfit_cards = OutfitCard.objects.filter(outfit_card_place=time_sheets_place_id)
        data = [{'id': oc.pk, 'name': oc.outfit_card_number} for oc in outfit_cards]
        return JsonResponse(data, safe=False)
    return JsonResponse([], safe=False)


class TimeSheetDetailView(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = TimeSheet
    permission_required = "hrdepartment_app.view_timesheet"


class TimeSheetListView(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = TimeSheet
    permission_required = "hrdepartment_app.view_timesheet"
    context_object_name = 'timesheets'

    def get(self, request, *args, **kwargs):
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['date', 'employee__title',
                           'time_sheets_place__name', 'notes', ]
            context = ajax_search(request, self, search_list, TimeSheet, query)
            return JsonResponse(context, safe=False)
        return super(TimeSheetListView, self).get(request, *args, **kwargs)


class TimeSheetDeleteView(PermissionRequiredMixin, LoginRequiredMixin, DeleteView):
    model = TimeSheet
    success_url = reverse_lazy('hrdepartment_app:timesheet_list')
    permission_required = "hrdepartment_app.delete_timesheet"


class OutfitCardReportView(PermissionRequiredMixin, LoginRequiredMixin):
    model = OutfitCard
    permission_required = "hrdepartment_app.view_outfitcard"
    template_name = 'hrdepartment_app/outfit_card_report.html'
    context_object_name = 'outfit_cards'

    def get_context_data(self, **kwargs):
        context = super(OutfitCardReportView, self).get_context_data(**kwargs)
        # context['outfit_cards'] = OutfitCard.objects.filter(employee=self.request.user)
        return context

# Журнал карт-наряда
class OutfitCardCreateView(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = OutfitCard
    form_class = OutfitCardForm
    success_url = reverse_lazy('hrdepartment_app:outfit_card_list')
    permission_required = "hrdepartment_app.create_outfitcard"

    def get_form_kwargs(self):
        kwargs = super(OutfitCardCreateView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

class OutfitCardUpdateView(PermissionRequiredMixin, LoginRequiredMixin, UpdateView): #UserPassesTestMixin, UpdateView):
    model = OutfitCard
    form_class = OutfitCardForm
    success_url = reverse_lazy('hrdepartment_app:outfit_card_list')
    permission_required = "hrdepartment_app.change_outfitcard"

    def get_form_kwargs(self):
        kwargs = super(OutfitCardUpdateView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    # def test_func(self):
    #     # Проверка, что текущий пользователь является автором карты-наряда
    #     return self.request.user == self.get_object().employee

class OutfitCardDetailView(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = OutfitCard
    permission_required = "hrdepartment_app.view_outfitcard"

class OutfitCardDeleteView(PermissionRequiredMixin, LoginRequiredMixin, DeleteView):
    model = OutfitCard
    success_url = reverse_lazy('hrdepartment_app:outfit_card_list')
    permission_required = "hrdepartment_app.delete_outfitcard"

    # def test_func(self):
    #     # Проверка, что текущий пользователь является автором карты-наряда
    #     return self.request.user == self.get_object().employee

class OutfitCardListView(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = OutfitCard
    context_object_name = 'outfit_cards'
    permission_required = "hrdepartment_app.view_outfitcard"

    def get(self, request, *args, **kwargs):
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['outfit_card_date', 'air_board__registration_number', 'works',
                           'outfit_card_number', 'workers', 'employee__title']
            context = ajax_search(request, self, search_list, OutfitCard, query)
            return JsonResponse(context, safe=False)
        return super(OutfitCardListView, self).get(request, *args, **kwargs)