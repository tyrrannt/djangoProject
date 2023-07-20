import datetime
from calendar import monthrange

from dateutil import rrule
from dateutil.relativedelta import relativedelta
from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from loguru import logger

from administration_app.models import PortalProperty
from administration_app.utils import change_session_context, change_session_queryset, change_session_get, FIO_format, \
    get_jsons_data, ending_day, get_history, get_year_interval
from customers_app.models import DataBaseUser, Counteragent
from hrdepartment_app.forms import MedicalExaminationAddForm, MedicalExaminationUpdateForm, OfficialMemoUpdateForm, \
    OfficialMemoAddForm, ApprovalOficialMemoProcessAddForm, ApprovalOficialMemoProcessUpdateForm, \
    BusinessProcessDirectionAddForm, BusinessProcessDirectionUpdateForm, MedicalOrganisationAddForm, \
    MedicalOrganisationUpdateForm, PurposeAddForm, PurposeUpdateForm, DocumentsOrderUpdateForm, DocumentsOrderAddForm, \
    DocumentsJobDescriptionUpdateForm, DocumentsJobDescriptionAddForm, PlaceProductionActivityAddForm, \
    PlaceProductionActivityUpdateForm, ApprovalOficialMemoProcessChangeForm, ReportCardAddForm, ReportCardUpdateForm, \
    ProvisionsUpdateForm, ProvisionsAddForm, OficialMemoCancelForm
from hrdepartment_app.hrdepartment_util import get_medical_documents, send_mail_change, get_month, \
    get_working_hours
from hrdepartment_app.models import Medical, OfficialMemo, ApprovalOficialMemoProcess, BusinessProcessDirection, \
    MedicalOrganisation, Purpose, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity, ReportCard, \
    ProductionCalendar, Provisions

logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'))


# Create your views here.
class MedicalOrganisationList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = MedicalOrganisation
    permission_required = 'customers_app.view_medicalorganisation'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            medicals = MedicalOrganisation.objects.all()
            data = [medical.get_data() for medical in medicals]
            response = {'data': data}
            return JsonResponse(response)
        count = 0
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "МедицинскиеОрганизации", 0)
            # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
            for item in todos['value']:
                if not item['DeletionMark']:
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'description': item['Description'],
                        'ogrn': item['ОГРН'],
                        'address': item['Адрес'],
                    }
                    MedicalOrganisation.objects.update_or_create(ref_key=item['Ref_Key'], defaults=divisions_kwargs)
            url_match = reverse_lazy('hrdepartment_app:medicalorg_list')
            return redirect(url_match)
        change_session_get(self.request, self)
        return super(MedicalOrganisationList, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Медицинские организации'
        return context


class MedicalOrganisationAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationAddForm
    permission_required = 'customers_app.add_medicalorganisation'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить медицинскую организацию'
        return context


class MedicalOrganisationUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationUpdateForm
    permission_required = 'customers_app.change_medicalorganisation'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class MedicalExamination(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = Medical
    permission_required = 'hrdepartment_app.view_medical'

    # paginate_by = 10
    # item_sorted = 'date_entry'
    # sorted_list = ['number', 'date_entry', 'person', 'person__user_work_profile__job__name', 'organisation',
    #                'type_inspection']

    def get_queryset(self):
        change_session_queryset(self.request, self)
        if self.item_sorted == 'date_entry':
            qs = super().get_queryset().order_by(self.item_sorted).reverse()
        else:
            qs = super().get_queryset().order_by(self.item_sorted)
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Медицинские направления'
        change_session_context(context, self)
        return context

    def get(self, request, *args, **kwargs):
        if self.request.GET.get('update') == '0':
            error = get_medical_documents()
            if error:
                return render(request, 'hrdepartment_app/medical_list.html',
                              {'error': 'Необходимо обновить список организаций.'})
            url_match = reverse_lazy('hrdepartment_app:medical_list')
            return redirect(url_match)
        change_session_get(self.request, self)
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            medical_list = Medical.objects.all().order_by("date_entry").reverse()
            data = [medical_item.get_data() for medical_item in medical_list]
            response = {'data': data}
            return JsonResponse(response)

        return super(MedicalExamination, self).get(request, *args, **kwargs)

    # @staticmethod
    # def ajax_get(request, *args, **kwargs):
    #     medicals = Medical.objects.all()
    #     data = [medical.get_data() for medical in medicals]
    #     response = {'data': data}
    #     return JsonResponse(response)


class MedicalExaminationAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = Medical
    form_class = MedicalExaminationAddForm
    permission_required = 'hrdepartment_app.add_medical'

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationAdd, self).get_context_data(**kwargs)
        content['all_person'] = DataBaseUser.objects.filter(type_users='staff_member')
        content['all_contragent'] = Counteragent.objects.all()
        content['all_status'] = Medical.type_of
        content['all_harmful'] = ''
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить медицинское направление'
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class MedicalExaminationUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Medical
    form_class = MedicalExaminationUpdateForm
    template_name = 'hrdepartment_app/medical_form_update.html'
    permission_required = 'hrdepartment_app.change_medical'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')


class OfficialMemoList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = OfficialMemo
    permission_required = 'hrdepartment_app.view_officialmemo'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if request.user.is_superuser or request.user.user_work_profile.job.type_of_job == '0':
                memo_list = OfficialMemo.objects.all().order_by('date_of_creation').reverse()
            else:
                memo_list = OfficialMemo.objects.filter(
                    Q(responsible__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job)).exclude(
                    comments='Документооборот завершен').order_by('date_of_creation').reverse()

            data = [memo_item.get_data() for memo_item in memo_list]
            response = {'data': data}
            return JsonResponse(response)
        return super(OfficialMemoList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(OfficialMemoList, self).get_queryset().order_by('pk')
        if not self.request.user.is_superuser:
            user_division = DataBaseUser.objects.get(pk=self.request.user.pk).user_work_profile.divisions
            qs = OfficialMemo.objects.filter(responsible__user_work_profile__divisions=user_division).order_by(
                'period_from').reverse()
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(OfficialMemoList, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Служебные записки'
        return context


class OfficialMemoAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = OfficialMemo
    form_class = OfficialMemoAddForm
    permission_required = 'hrdepartment_app.add_officialmemo'

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoAdd, self).get_context_data(**kwargs)
        # content['all_status'] = OfficialMemo.type_of_accommodation
        # Генерируем список сотрудников, которые на текущий момент времени не находятся в СП
        users_list = [person.person_id for person in OfficialMemo.objects.filter(
            Q(period_from__lte=datetime.datetime.today()) & Q(period_for__gte=datetime.datetime.today()))]
        # Выбераем из базы тех сотрудников, которые содержатся в списке users_list и исключаем из него суперпользователя
        # content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(pk__in=users_list).exclude(is_superuser=True)
        user_job = self.request.user

        content['form'].fields['person'].queryset = DataBaseUser.objects.filter(
            user_work_profile__job__type_of_job=user_job.user_work_profile.job.type_of_job).exclude(
            username='proxmox').exclude(is_active=False).order_by('last_name')
        content['form'].fields['place_production_activity'].queryset = PlaceProductionActivity.objects.all()
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить служебную записку'
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
        memo_type = request.GET.get('memo_type', None)
        try:
            person = DataBaseUser.objects.get(pk=employee)
            division = str(person.user_work_profile.divisions)
        except DataBaseUser.DoesNotExist:
            pass
        if memo_type and employee:
            html = {'employee': '', 'memo_type': ''}
            if memo_type == '2':
                memo_list = OfficialMemo.objects.filter(
                    Q(person=employee) & Q(official_memo_type='1') & Q(docs__accepted_accounting=False)).exclude(
                    cancellation=True)
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                html['memo_type'] = memo_obj_list
                html['employee'] = division
                return JsonResponse(html)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, '%Y-%m-%d')
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date)).exclude(cancellation=True)
            try:
                filter_string = datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
                for item in filters:
                    if item.period_for > filter_string:
                        filter_string = item.period_for
            except AttributeError:
                logger.info(
                    f'За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}')
            if filters.count() > 0:
                # html = filter_string + datetime.timedelta(days=1)
                label = 'Внимание, в заданный интервал имеются другие СЗ:'
                for item in filters:
                    label += ' ' + str(item) + ';'
                html = label
                return JsonResponse(html, safe=False)
        # Согласно приказу, ограничиваем последним днем предыдущего и первым днем следующего месяцев
        interval = request.GET.get('interval', None)
        if interval:
            request_day = datetime.datetime.strptime(interval, '%Y-%m-%d').day
            request_month = datetime.datetime.strptime(interval, '%Y-%m-%d').month
            request_year = datetime.datetime.strptime(interval, '%Y-%m-%d').year
            current_days = monthrange(request_year, request_month)[1]
            if request_month < 12:
                next_days = monthrange(request_year, request_month + 1)[1]
                next_month = request_month + 1
                next_year = request_year
            else:
                next_days = monthrange(request_year + 1, 1)[1]
                next_month = 1
                next_year = request_year + 1
            min_date = datetime.datetime.strptime(interval, '%Y-%m-%d')
            if request_day == current_days:
                if request_month == 11:
                    max_date = datetime.datetime.strptime(f'{next_year + 1}-{"01"}-{"01"}', '%Y-%m-%d')
                    dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
                else:
                    max_date = datetime.datetime.strptime(f'{next_year}-{next_month + 1}-{"01"}', '%Y-%m-%d')
                    dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
            else:
                max_date = datetime.datetime.strptime(f'{next_year}-{next_month}-{"01"}', '%Y-%m-%d')
                dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
            return JsonResponse(dict_obj, safe=False)
        if employee:
            return JsonResponse(division, safe=False)
        return super(OfficialMemoAdd, self).get(request, *args, **kwargs)


class OfficialMemoDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = OfficialMemo
    permission_required = 'hrdepartment_app.view_officialmemo'

    def get_context_data(self, **kwargs):
        content = super().get_context_data(**kwargs)
        content['change_history'] = get_history(self, OfficialMemo)
        return content


class OfficialMemoCancel(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    permission_required = 'hrdepartment_app.change_officialmemo'
    template_name = 'hrdepartment_app/officialmemo_form_cancel.html'
    form_class = OficialMemoCancelForm

    def get_context_data(self, **kwargs):
        content = super().get_context_data(**kwargs)
        content['change_history'] = get_history(self, OfficialMemo)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

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
        kwargs.update({'cancel': cancel})
        return kwargs


class OfficialMemoUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    template_name = 'hrdepartment_app/officialmemo_form_update.html'
    permission_required = 'hrdepartment_app.change_officialmemo'

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        # Получаем объект
        obj_item = self.get_object()
        obj_list = OfficialMemo.objects.filter(
            Q(person=obj_item.person) & Q(official_memo_type='1') & Q(docs__accepted_accounting=False))
        # Получаем разницу в днях, для определения количества дней СП
        delta = (self.object.period_for - self.object.period_from)
        # Передаем количество дней в контекст
        content['period'] = int(delta.days) + 1
        # Получаем все служебные записки по человеку, исключая текущую
        filters = OfficialMemo.objects.filter(person=self.object.person).exclude(pk=self.object.pk).exclude(
            cancellation=True)
        filter_string = {
            "pk": 0,
            "period": datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
        }
        # Проходимся по выборке в цикле
        for item in filters:
            if item.period_for > filter_string["period"]:
                filter_string["pk"] = item.pk
                filter_string["period"] = item.period_for

        content['form'].fields['place_production_activity'].queryset = PlaceProductionActivity.objects.all()
        if obj_item.official_memo_type == '2':
            content['form'].fields['document_extension'].queryset = obj_list
        else:
            content['form'].fields['document_extension'].queryset = OfficialMemo.objects.filter(pk=0).exclude(
                cancellation=True)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.object}'
        content['change_history'] = get_history(self, OfficialMemo)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)

    def form_valid(self, form):
        critical_change = 0
        warning_change = 0

        def person_finder(item, instanse_obj):
            person_list = ['person_id']
            date_field = ['period_from', 'period_for']
            if item in person_list:
                return DataBaseUser.objects.get(pk=instanse_obj[item])
            if item in date_field:
                return instanse_obj[item].strftime('%d.%m.%Y')
            if item == 'purpose_trip_id':
                return Purpose.objects.get(pk=instanse_obj[item])
            else:
                return instanse_obj[item]

        if form.is_valid():
            # в old_instance сохраняем старые значения записи
            object_item = self.get_object()
            place_old = set([item.name for item in object_item.place_production_activity.all()])

            old_instance = object_item.__dict__
            refresh_form = form.save(commit=False)
            if refresh_form.official_memo_type == '1':
                refresh_form.document_extension = None
            refresh_form.save()
            form.save_m2m()
            object_item = self.get_object()
            # в new_instance сохраняем новые значения записи
            new_instance = object_item.__dict__
            place_new = set([item.name for item in object_item.place_production_activity.all()])
            changed = False
            # создаем генератор списка
            diffkeys = [k for k in old_instance if old_instance[k] != new_instance[k]]
            message = '<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:<br>'
            # print(diffkeys)
            if place_old != place_new:
                critical_change = 1
                message += f'Место назначения: <strike>{place_old}</strike> -> {place_new}<br>'
                changed = True
            # Доработать замену СЗ
            for k in diffkeys:
                # print(k)
                if k != '_state':
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
                    if k == 'person_id':
                        critical_change = 1
                    if k == 'period_from':
                        if new_instance[k] < old_instance[k]:
                            critical_change = 1
                        else:
                            warning_change = 1
                    if k == 'period_for':
                        if (new_instance[k] != old_instance[k]) and (
                                str(object_item.purpose_trip) == 'Прохождения курсов повышения квалификации (КПК)'):
                            critical_change = 1
                        warning_change = 1
                    if k == 'type_trip':
                        warning_change = 1
                    if k == 'purpose_trip_id':
                        warning_change = 1
                    message += f'{object_item._meta.get_field(k).verbose_name}: <strike>{person_finder(k, old_instance)}</strike> -> {person_finder(k, new_instance)}<br>'
                    changed = True
            get_obj = self.get_object()

            if changed:
                object_item.history_change.create(author=self.request.user, body=message)
                if critical_change == 1:
                    try:
                        get_bpmemo_obj = ApprovalOficialMemoProcess.objects.get(pk=object_item.docs.pk)
                        if object_item.order:
                            get_order_obj = object_item.order
                        else:
                            get_order_obj = ''
                        if get_order_obj != '':
                            # ToDo: Сделать обработку отправки письма
                            send_mail_change(1, get_obj, message)
                            if get_obj.period_for < datetime.datetime.now().date():
                                get_bpmemo_obj.location_selected = False
                                get_bpmemo_obj.accommodation = ''
                                get_obj.accommodation = ''
                            get_bpmemo_obj.process_accepted = False
                            get_bpmemo_obj.email_send = False
                            get_bpmemo_obj.order = None
                            get_order_obj.cancellation = True
                            get_obj.document_accepted = False
                            get_obj.order = None
                            get_obj.comments = 'Документ согласован'
                            get_obj.save()
                            get_bpmemo_obj.save()
                            get_order_obj.save()
                        else:
                            # ToDo: Сделать обработку отправки письма
                            send_mail_change(2, get_obj, message)
                            get_bpmemo_obj.location_selected = False
                            get_bpmemo_obj.accommodation = ''
                            get_obj.comments = 'Документ согласован'
                            get_obj.save()
                            get_bpmemo_obj.save()
                    except Exception as _ex:
                        print(_ex)
                else:
                    if warning_change == 1:
                        send_mail_change(3, get_obj, message)
            return HttpResponseRedirect(reverse('hrdepartment_app:memo_list'))

        else:
            logger.info(f'{form.errors}')

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
        memo_type = request.GET.get('memo_type', None)
        """
        Функция memo_type_change() в officialmemo_form_update.html. Если в качестве типа служебной записки указывается
        продление, то происходит выборка служебных записок с полями Сотрудник = Сотрудник, Тип СЗ = направление
        и поле Принят в бухгалтерию у бизнес процесса по этим СЗ не равно Истина. Поле документ основание заполняется 
        и в форме появляется возможность выбора
        """
        if memo_type and employee:
            if memo_type == '2':
                memo_list = OfficialMemo.objects.filter(
                    Q(person=employee) & Q(official_memo_type='1') & Q(docs__accepted_accounting=False)).exclude(
                    pk=self.get_object().pk).exclude(cancelation=True)
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                return JsonResponse(memo_obj_list)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, '%Y-%m-%d')
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date)).exclude(cancelation=True)
            try:
                filter_string = datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
                for item in filters:
                    if item.period_for > filter_string:
                        filter_string = item.period_for
            except AttributeError:
                logger.info(
                    f'За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}')
            if filters.count() > 0:
                html = filter_string + datetime.timedelta(days=1)
                return JsonResponse(html, safe=False)
        # Согласно приказу, ограничиваем последним днем предыдущего и первым днем следующего месяцев
        interval = request.GET.get('interval', None)
        period_for_value = request.GET.get('pfv', None)
        if interval:
            request_day = datetime.datetime.strptime(interval, '%Y-%m-%d').day
            request_month = datetime.datetime.strptime(interval, '%Y-%m-%d').month
            request_year = datetime.datetime.strptime(interval, '%Y-%m-%d').year
            current_days = monthrange(request_year, request_month)[1]

            if request_month < 12:
                next_days = monthrange(request_year, request_month + 1)[1]
                next_month = request_month + 1
                next_year = request_year
            else:
                next_days = monthrange(request_year + 1, 1)[1]
                next_month = 1
                next_year = request_year + 1
            min_date = datetime.datetime.strptime(interval, '%Y-%m-%d')
            if request_day == current_days:
                if request_month == 11:
                    max_date = datetime.datetime.strptime(f'{next_year + 1}-{"01"}-{"01"}', '%Y-%m-%d')
                    dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
                else:
                    max_date = datetime.datetime.strptime(f'{next_year}-{next_month + 1}-{"01"}', '%Y-%m-%d')
                    dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
            else:
                max_date = datetime.datetime.strptime(f'{next_year}-{next_month}-{"01"}', '%Y-%m-%d')
                dict_obj = [min_date.strftime("%Y-%m-%d"), max_date.strftime("%Y-%m-%d")]
            if datetime.datetime.strptime(period_for_value, '%Y-%m-%d') > max_date:
                # period_for_value = max_date
                dict_obj.append(max_date)
            else:
                dict_obj.append(period_for_value)
            return JsonResponse(dict_obj, safe=False)
        return super(OfficialMemoUpdate, self).get(request, *args, **kwargs)


class ApprovalOficialMemoProcessList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess
    permission_required = 'hrdepartment_app.view_approvaloficialmemoprocess'

    def get_queryset(self):
        qs = super(ApprovalOficialMemoProcessList, self).get_queryset()
        if not self.request.user.is_superuser:
            user_division = DataBaseUser.objects.get(pk=self.request.user.pk).user_work_profile.divisions

            qs = ApprovalOficialMemoProcess.objects.filter(
                Q(person_agreement__user_work_profile__divisions=user_division) |
                Q(person_distributor__user_work_profile__divisions=user_division) |
                Q(person_executor__user_work_profile__divisions=user_division) |
                Q(person_department_staff__user_work_profile__divisions=user_division)).order_by('pk')
        return qs

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if request.user.is_superuser or request.user.user_work_profile.job.type_of_job == '0':
                approvalmemo_list = ApprovalOficialMemoProcess.objects.all().order_by('document__period_from').reverse()
            else:
                approvalmemo_list = ApprovalOficialMemoProcess.objects.filter(
                    person_executor__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job).order_by(
                    'document__period_from').reverse()
            data = [approvalmemo_item.get_data() for approvalmemo_item in approvalmemo_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // БП по служебным поездкам'
        return context


class ApprovalOficialMemoProcessAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm
    permission_required = 'hrdepartment_app.add_approvaloficialmemoprocess'

    def get_context_data(self, **kwargs):
        global person_agreement_list
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)
        content['form'].fields['document'].queryset = OfficialMemo.objects.filter(
            Q(docs__isnull=True) & Q(responsible=self.request.user)).exclude(cancellation=True)
        business_process = BusinessProcessDirection.objects.filter(
            person_executor=self.request.user.user_work_profile.job)
        users_list = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
        # Для поля Исполнитель, делаем выборку пользователя из БД на основе request
        content['form'].fields['person_executor'].queryset = users_list.filter(pk=self.request.user.pk)

        person_agreement_list = list()
        content['form'].fields['person_agreement'].queryset = users_list.filter(
            user_work_profile__job__pk__in=person_agreement_list)
        for item in business_process:
            if item.person_executor.filter(name__contains=self.request.user.user_work_profile.job.name):
                person_agreement_list = [items[0] for items in item.person_agreement.values_list()]
                content['form'].fields['person_agreement'].queryset = users_list.filter(
                    user_work_profile__job__pk__in=person_agreement_list)
        # content['form'].fields['person_distributor'].queryset = users_list.filter(
        #     Q(user_work_profile__divisions__type_of_role='1') & Q(user_work_profile__job__right_to_approval=True) &
        #     Q(is_superuser=False))
        # content['form'].fields['person_department_staff'].queryset = users_list.filter(
        #     Q(user_work_profile__divisions__type_of_role='2') & Q(user_work_profile__job__right_to_approval=True) &
        #     Q(is_superuser=False))
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить БП по СП'
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')

    def form_valid(self, form):
        if form.is_valid():
            refresh_form = form.save(commit=False)
            refresh_form.start_date_trip = refresh_form.document.period_from
            refresh_form.end_date_trip = refresh_form.document.period_for
            refresh_form.save()
        return super().form_valid(form)


class ApprovalOficialMemoProcessUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessUpdateForm
    template_name = 'hrdepartment_app/approvaloficialmemoprocess_form_update.html'
    permission_required = 'hrdepartment_app.change_approvaloficialmemoprocess'

    def get_queryset(self):
        qs = ApprovalOficialMemoProcess.objects.all().select_related('person_executor', 'person_agreement',
                                                                     'person_distributor', 'person_department_staff',
                                                                     'person_clerk', 'person_hr', 'person_accounting',
                                                                     'document', 'order')
        return qs

    def get_context_data(self, **kwargs):
        global person_agreement_list

        users_list = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
        content = super(ApprovalOficialMemoProcessUpdate, self).get_context_data(**kwargs)
        document = self.get_object()
        business_process = BusinessProcessDirection.objects.filter(
            person_executor=document.person_executor.user_work_profile.job)
        content['document'] = document.document
        person_agreement_list = list()
        person_clerk_list = list()
        person_hr_list = list()
        for item in business_process:
            person_agreement_list = [items[0] for items in item.person_agreement.values_list()]
            person_clerk_list = [items[0] for items in item.clerk.values_list()]
            person_hr_list = [items[0] for items in item.person_hr.values_list()]
        # Получаем подразделение исполнителя
        # division = document.person_executor.user_work_profile.divisions
        # При редактировании БП фильтруем поле исполнителя, чтоб нельзя было изменить его в процессе работы
        content['form'].fields['person_executor'].queryset = users_list.filter(pk=document.person_executor.pk)
        # Если установлен признак согласования документа, то фильтруем поле согласующего лица
        if document.document_not_agreed:
            try:
                content['form'].fields['person_agreement'].queryset = users_list.filter(
                    pk=document.person_agreement.pk)
            except AttributeError:
                content['form'].fields['person_agreement'].queryset = users_list.filter(
                    user_work_profile__job__pk__in=person_agreement_list)
        else:
            # Иначе по подразделению исполнителя фильтруем руководителей для согласования
            content['form'].fields['person_agreement'].queryset = users_list.filter(
                user_work_profile__job__pk__in=person_agreement_list)
            try:
                # Если пользователь = Согласующее лицо
                if self.request.user.user_work_profile.job.pk in person_agreement_list:
                    content['form'].fields['person_agreement'].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_agreement_list) & Q(pk=self.request.user.pk))
                # Иначе весь список согласующих лиц
                else:
                    content['form'].fields['person_agreement'].queryset = users_list.filter(
                        user_work_profile__job__pk__in=person_agreement_list)
            except AttributeError as _ex:
                logger.error(f'У пользователя отсутствует должность')
                # ToDo: Нужно вставить выдачу ошибки
                return {}

        list_agreement = list()
        for unit in users_list.filter(user_work_profile__job__pk__in=person_agreement_list):
            list_agreement.append(unit.pk)
        content['list_agreement'] = list_agreement

        list_distributor = users_list.filter(
            Q(user_work_profile__divisions__type_of_role='1') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))

        content['form'].fields['person_distributor'].queryset = list_distributor
        content['list_distributor'] = list_distributor

        list_department_staff = users_list.filter(
            Q(user_work_profile__divisions__type_of_role='2') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        content['form'].fields['person_department_staff'].queryset = list_department_staff
        content['list_department_staff'] = list_department_staff

        list_accounting = users_list.filter(
            Q(user_work_profile__divisions__type_of_role='3') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        content['form'].fields['person_accounting'].queryset = list_accounting
        content['list_accounting'] = list_accounting

        list_clerk = users_list.filter(user_work_profile__job__pk__in=person_clerk_list)
        if document.originals_received:
            try:
                content['form'].fields['person_clerk'].queryset = users_list.filter(
                    pk=document.person_clerk.pk)
            except AttributeError:
                content['form'].fields['person_clerk'].queryset = list_clerk
        else:
            # Иначе по подразделению исполнителя фильтруем делопроизводителя для согласования
            content['form'].fields['person_clerk'].queryset = list_clerk
            try:
                # Если пользователь = Делопроизводитель
                if self.request.user.user_work_profile.job.pk in person_clerk_list:
                    content['form'].fields['person_clerk'].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_clerk_list) & Q(pk=self.request.user.pk))
                # Иначе весь список делопроизводителей
                else:
                    content['form'].fields['person_clerk'].queryset = list_clerk
            except AttributeError as _ex:
                logger.error(f'У пользователя отсутствует должность')
                # ToDo: Нужно вставить выдачу ошибки
                return {}
        content['list_clerk'] = list_clerk

        list_hr = users_list.filter(user_work_profile__job__pk__in=person_hr_list)
        if document.originals_received:
            try:
                content['form'].fields['person_hr'].queryset = users_list.filter(
                    pk=document.person_hr.pk)
            except AttributeError:
                content['form'].fields['person_hr'].queryset = list_hr
        else:
            # Иначе по подразделению исполнителя фильтруем сотрудника ОК для согласования
            content['form'].fields['person_hr'].queryset = list_hr
            try:
                # Если пользователь = Сотрудник ОК
                if self.request.user.user_work_profile.job.pk in person_hr_list:
                    content['form'].fields['person_hr'].queryset = users_list.filter(
                        Q(user_work_profile__job__pk__in=person_hr_list) & Q(pk=self.request.user.pk))
                # Иначе весь список сотрудников ОК
                else:
                    content['form'].fields['person_hr'].queryset = list_hr
            except AttributeError as _ex:
                logger.error(f'У пользователя отсутствует должность')
                # ToDo: Нужно вставить выдачу ошибки
                return {}
        content['list_hr'] = list_hr

        content[
            'title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {document.document.title}'
        # Выбираем приказ
        if document.document.official_memo_type == '1':
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.pk).exclude(cancellation=True)
        elif document.document.official_memo_type == '2':
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.pk).exclude(cancellation=True)
        else:
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(pk=0)
        delta = document.document.period_for - document.document.period_from
        content['ending_day'] = ending_day(int(delta.days) + 1)
        content['change_history'] = get_history(self, ApprovalOficialMemoProcess)
        content['without_departure'] = False if document.document.official_memo_type == '3' else True
        content['extension'] = False if document.document.official_memo_type == '2' else True
        # print(document.prepaid_expense_summ - (document.number_business_trip_days*500 + document.number_flight_days*900))
        return content

    def form_valid(self, form):

        def person_finder(object_item, item, instanse_obj):
            person_list = ['Исполнитель', 'Согласующее лицо', 'Сотрудник НО', 'Сотрудник ОК', 'Сотрудник Бухгалтерии',
                           'Делопроизводитель']
            if object_item._meta.get_field(k).verbose_name in person_list:
                if instanse_obj[item]:
                    return DataBaseUser.objects.get(pk=instanse_obj[item])
                else:
                    return 'Пустое значение'
            else:
                if instanse_obj[item] == True:
                    return 'Да'
                elif instanse_obj[item] == False:
                    return 'Нет'
                else:
                    return instanse_obj[item]

        if form.is_valid():
            object_item = self.get_object()
            # в old_instance сохраняем старые значения записи
            old_instance = object_item.__dict__
            if object_item.document.official_memo_type == '2':
                refresh_form = form.save(commit=False)
                refresh_form.hr_accepted = object_item.hr_accepted
                refresh_form.person_accounting = object_item.person_accounting
                refresh_form.accepted_accounting = object_item.accepted_accounting
                refresh_form.date_receipt_original = object_item.date_receipt_original
                refresh_form.submitted_for_signature = object_item.submitted_for_signature
                refresh_form.date_transfer_hr = object_item.date_transfer_hr
                refresh_form.number_business_trip_days = object_item.number_business_trip_days
                refresh_form.number_flight_days = object_item.number_flight_days
                refresh_form.person_hr = object_item.person_hr
                refresh_form.start_date_trip = object_item.start_date_trip
                refresh_form.end_date_trip = object_item.end_date_trip
                refresh_form.date_transfer_accounting = object_item.date_transfer_accounting
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
                        approval_process_item = ApprovalOficialMemoProcess.objects.get(document=item)
                        approval_process_item.hr_accepted = object_item.hr_accepted
                        approval_process_item.person_accounting = object_item.person_accounting
                        approval_process_item.accepted_accounting = object_item.accepted_accounting
                        approval_process_item.date_receipt_original = object_item.date_receipt_original
                        approval_process_item.submitted_for_signature = object_item.submitted_for_signature
                        approval_process_item.date_transfer_hr = object_item.date_transfer_hr
                        approval_process_item.number_business_trip_days = object_item.number_business_trip_days
                        approval_process_item.number_flight_days = object_item.number_flight_days
                        approval_process_item.person_hr = object_item.person_hr
                        approval_process_item.start_date_trip = item.period_from
                        approval_process_item.end_date_trip = object_item.end_date_trip
                        approval_process_item.date_transfer_accounting = object_item.date_transfer_accounting
                        approval_process_item.prepaid_expense_summ = object_item.prepaid_expense_summ
                        document = approval_process_item.document
                        document.comments = 'Документооборот завершен'
                        document.save()
                        approval_process_item.save()
                    except Exception as _ex:
                        logger.warning(f'{_ex}: Документ - {object_item}')
            # в new_instance сохраняем новые значения записи
            new_instance = object_item.__dict__
            changed = False
            # создаем генератор списка
            diffkeys = [k for k in old_instance if old_instance[k] != new_instance[k]]
            message = '<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:\n'
            for k in diffkeys:
                if k != '_state':
                    message += f'{object_item._meta.get_field(k).verbose_name}: <strike>{person_finder(object_item, k, old_instance)}</strike> -> {person_finder(object_item, k, new_instance)}\n'
                    changed = True
            if changed:
                object_item.history_change.create(author=self.request.user, body=message)

            return HttpResponseRedirect(reverse('hrdepartment_app:bpmemo_list'))
        else:
            logger.info(f'{form.errors}')

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
        order = request.POST.get('order')
        accommodation = request.POST.get('accommodation')
        change_status = 0
        document = OfficialMemo.objects.get(pk=self.get_object().document.pk)
        if document.order != order:
            # Если добавлен или изменен приказ, сохраняем его в документ Служебной записки
            if order != '':
                document.order = DocumentsOrder.objects.get(pk=order)
                change_status = 1

        if document.accommodation != accommodation:
            # Если добавлено или изменено место проживания, сохраняем его в документ Служебной записки
            if accommodation:
                document.accommodation = accommodation
                change_status = 1

        if change_status > 0:
            if document.cancellation:
                document.comments = 'Документ отменен'
            document.save()
        return super().post(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.GET.get('send') == '0':
            obj_item = self.get_object()
            obj_item.send_mail(title='Повторное уведомление', trigger=1)
            # return redirect('hrdepartment_app:bpmemo_update', obj_item.pk)
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')


class ApprovalOficialMemoProcessCancel(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessChangeForm
    template_name = 'hrdepartment_app/approvaloficialmemoprocess_form_cancel.html'

    def form_valid(self, form):
        if form.is_valid():
            form.save()
            obj_item = self.get_object()
            official_memo = obj_item.document
            order = obj_item.order
            try:
                if official_memo:
                    OfficialMemo.objects.filter(pk=official_memo.pk).update(cancellation=True,
                                                                            reason_cancellation=obj_item.reason_cancellation,
                                                                            comments='Документ отменен')
                if order:
                    DocumentsOrder.objects.filter(pk=order.pk).update(cancellation=True,
                                                                      reason_cancellation=obj_item.reason_cancellation)
                    print('Отменен')
                obj_item.send_mail(title='Уведомление об отмене')
            except Exception as _ex:
                logger.error(f'Ошибка при отмене БП {_ex}')

        return super().form_valid(form)


class ApprovalOficialMemoProcessReportList(LoginRequiredMixin, ListView):
    """
    Контроль закрытых служебных поездок
    """
    model = ApprovalOficialMemoProcess
    template_name = 'hrdepartment_app/approvaloficialmemoprocess_report_list.html'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get('report_month')
        current_year = self.request.GET.get('report_year')
        if current_month and current_year:
            request.session['current_month'] = int(current_month)
            request.session['current_year'] = int(current_year)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session['current_month'] and request.session['current_year']:
                start_date = datetime.date(year=int(request.session['current_year']),
                                           month=int(request.session['current_month']), day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))

                if request.user.is_superuser or request.user.user_work_profile.job.type_of_job == '0':
                    reportcard_list = ApprovalOficialMemoProcess.objects.filter(
                        Q(document__period_for__in=search_interval)).exclude(
                        document__comments__in=['Документооборот завершен', 'Передано в ОК',
                                                'Передано в бухгалтерию']).exclude(
                        document__official_memo_type__in=['2', '3']).exclude(cancellation=True).order_by(
                        'document__period_for').reverse()
                else:
                    reportcard_list = ApprovalOficialMemoProcess.objects.filter(
                        Q(document__period_for__in=search_interval) &
                        Q(person_executor__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job)).exclude(
                        document__comments__in=['Документооборот завершен', 'Передано в ОК',
                                                'Передано в бухгалтерию']).exclude(
                        document__official_memo_type__in=['2', '3']).exclude(cancellation=True).order_by(
                        'document__period_for').reverse()


            else:
                start_date = datetime.date(year=datetime.datetime.today().year,
                                           month=datetime.datetime.today().month, day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                if request.user.is_superuser or request.user.user_work_profile.job.type_of_job == '0':
                    reportcard_list = ApprovalOficialMemoProcess.objects.filter(
                        Q(document__period_for__in=search_interval)).exclude(
                        document__comments__in=['Документооборот завершен', 'Передано в ОК',
                                                'Передано в бухгалтерию']).exclude(
                        document__official_memo_type__in=['2', '3']).exclude(cancellation=True).order_by(
                        'document__period_for').reverse()
                else:
                    reportcard_list = ApprovalOficialMemoProcess.objects.filter(
                        Q(document__period_for__in=search_interval) &
                        Q(person_executor__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job)).exclude(
                        document__comments__in=['Документооборот завершен', 'Передано в ОК',
                                                'Передано в бухгалтерию']).exclude(
                        document__official_memo_type__in=['2', '3']).exclude(cancellation=True).order_by(
                        'document__period_for').reverse()
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['current_year'] = self.request.session['current_year']
        context['current_month'] = str(self.request.session['current_month'])
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Бизнес процессы списком'
        return context


class PurposeList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = Purpose
    permission_required = 'hrdepartment_app.view_purpose'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            purpose_list = Purpose.objects.all()
            data = [purpose_item.get_data() for purpose_item in purpose_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Цели служебных поездок'
        return context


class PurposeAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = Purpose
    form_class = PurposeAddForm
    permission_required = 'hrdepartment_app.add_purpose'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить цель СП'
        return context


class PurposeUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Purpose
    form_class = PurposeUpdateForm
    permission_required = 'hrdepartment_app.change_purpose'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class BusinessProcessDirectionList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = BusinessProcessDirection
    permission_required = 'hrdepartment_app.view_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Направление бизнес-процессов'
        return context


class BusinessProcessDirectionAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionAddForm
    permission_required = 'hrdepartment_app.add_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить направление БП'
        return context


class BusinessProcessDirectionUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionUpdateForm
    permission_required = 'hrdepartment_app.change_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class ReportApprovalOficialMemoProcessList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
        Отчет по сотрудникам
    """
    model = ApprovalOficialMemoProcess
    template_name = 'hrdepartment_app/reportapprovaloficialmemoprocess_list.html'
    permission_required = 'hrdepartment_app.view_approvaloficialmemoprocess'

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('hrdepartment_app:bpmemo_report'))

    def get_queryset(self):
        qs = super(ReportApprovalOficialMemoProcessList, self).get_queryset()
        return qs

    def get(self, request, *args, **kwargs):
        # Получаем выборку из базы данных, если был изменен один из параметров

        if self.request.GET:
            current_year = int(self.request.GET.get('CY'))
            current_month = int(self.request.GET.get('CM'))
            html_obj = ''
            report = []
            from calendar import monthrange
            days = monthrange(current_year, current_month)[1]
            date_start = datetime.datetime.strptime(f'{current_year}-{current_month}-01', '%Y-%m-%d')
            date_end = datetime.datetime.strptime(f'{current_year}-{current_month}-{days}', '%Y-%m-%d')

            if self.request.user.user_work_profile.divisions.type_of_role == '2':
                report_query = ReportCard.objects.filter(
                    Q(report_card_day__gte=date_start) & Q(report_card_day__lte=date_end)).order_by(
                    'employee__last_name')
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
                    Q(employee__user_work_profile__job__type_of_job=self.request.user.user_work_profile.job.type_of_job)
                    & Q(report_card_day__gte=date_start) & Q(report_card_day__lte=date_end)).order_by(
                    'employee__last_name')
            dict_obj = dict()
            dist = report_query.values('employee__title').distinct()
            for rec in dist:
                list_obj = []
                selected_record = report_query.filter(employee__title=rec['employee__title'])
                person = FIO_format(rec['employee__title'])
                if person not in dict_obj:
                    dict_obj[person] = []
                for days_count in range(0, (date_end - date_start).days + 1):
                    place = ''
                    curent_day = date_start + datetime.timedelta(days_count)
                    if selected_record.filter(report_card_day=curent_day.date()).exists():
                        if selected_record.filter(report_card_day=curent_day.date()).count() == 1:
                            obj = selected_record.filter(report_card_day=curent_day.date()).first()
                            place = '; '.join([item.name for item in obj.place_report_card.all()])
                            if place == '':
                                place = obj.get_record_type_display()
                            trigger = '2' if obj.confirmed else '1'
                            list_obj.append([trigger, place, obj.record_type])
                        else:
                            for item in selected_record.filter(report_card_day=curent_day.date()):
                                place += item.get_record_type_display() + '; '
                            trigger = '3'
                            list_obj.append([trigger, place, ''])
                    else:
                        list_obj.append(['0', '', ''])

                dict_obj[person] = list_obj

                table_set = dict_obj
                html_table_count = ''
                table_count = range(1, (date_end - date_start).days + 2)
                for item in table_count:
                    html_table_count += f'<th width="2%" style="position: -webkit-sticky;  position: sticky;  top: -3px; z-index: 2; background: #ffffff"><span style="color: #0a53be">{item}</span></th>'
                html_table_set = ''
                color = ['f5f5dc', '49c144', 'ff0000', 'a0dfbd', 'FFCC00', 'ffff00', '9d76f5', 'ff8fa2', '808080', '76e3f5', '46aef2']
                for key, value in table_set.items():
                    html_table_set += f'<tr><td width="14%" style="position: -webkit-sticky;  position: sticky;"><strong>{key}</strong></td>'
                    for unit in value:
                        match unit[0]:
                            case '1':
                                place = unit[1].replace('"', "")
                                match unit[2]:
                                    case '1':
                                        plase_short = 'Я'
                                        cnt = 9
                                    case '13':
                                        plase_short = 'РВ'
                                        cnt = 10
                                    case '14':
                                        plase_short = 'СП'
                                        cnt = 3
                                    case '15':
                                        plase_short = 'К'
                                        cnt = 3
                                    case '2':
                                        plase_short = 'О'
                                        cnt = 4
                                    case '3' | '5' | '7' | '10' | '11':
                                        plase_short = 'ДО'
                                        cnt = 5
                                    case '16':
                                        plase_short = 'Б'
                                        cnt = 6
                                    case '17':
                                        plase_short = 'М'
                                        cnt = 7
                                    case _:
                                        plase_short = ''
                                        cnt = 8
                                html_table_set += f'<td width="2%" style="background-color: #{color[cnt]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}">{plase_short}</td>'
                            case '2':
                                place = unit[1].replace('"', "")
                                match unit[2]:
                                    case '14':
                                        plase_short = 'СП'
                                        cnt = 1
                                    case '15':
                                        plase_short = 'К'
                                        cnt = 1
                                html_table_set += f'<td width="2%" style="background-color: #{color[cnt]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}"><strong>{plase_short}</strong></td>'
                            case '3':
                                place = unit[1].replace('"', "")
                                plase_short = ''  # unit[2]
                                html_table_set += f'<td width="2%" style="background-color: #{color[2]}; border-color:#4670ad;border-style:dashed;border-width:1px;" class="position-4-success" fio="{key}" title="{place}">{plase_short}</td>'
                            case _:
                                html_table_set += f'<td width="2%" style="background-color: #{color[0]}; border-color:#4670ad;border-style:dashed;border-width:1px;"></td>'
                    html_table_set += '</tr>'

                job_type = {
                    '0': 'Общий состав',
                    '1': 'Летный состав',
                    '2': 'Инженерный состав',
                    '3': 'Транспортный отдел',
                }
                report_item_obj = f'<td colspan="{len(table_count) + 1}"><h4>'
                counter = 0
                for report_item in report:
                    report_item_obj += f'{job_type[str(counter)]}: {report_item};&nbsp;'
                    counter += 1
                report_item_obj += '</h4></td>'
                html_obj = f'''<table class="table table-ecommerce-simple table-striped mb-0" id="id_datatable" style="min-width: 1000px; display: block; height: 500px; overflow: auto;">
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
                            </table>'''

            return JsonResponse(html_obj, safe=False)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        content = super().get_context_data(**kwargs)

        if self.request.GET:
            current_year = int(self.request.GET.get('CY'))
            current_month = int(self.request.GET.get('CM'))
        else:
            current_year = datetime.datetime.now().year
            current_month = datetime.datetime.now().month
        from calendar import monthrange
        days = monthrange(current_year, current_month)[1]
        date_start = datetime.datetime.strptime(f'{current_year}-{current_month}-01', '%Y-%m-%d')
        date_end = datetime.datetime.strptime(f'{current_year}-{current_month}-{days}', '%Y-%m-%d')

        # qs = ApprovalOficialMemoProcess.objects.filter(Q(person_executor__pk=self.request.user.pk) & (
        #         Q(document__period_from__lte=date_start) | Q(document__period_from__lte=date_end)) & Q(
        #     document__period_for__gte=date_start)).order_by('document__period_from')
        if self.request.user.user_work_profile.divisions.type_of_role == '2':
            qs = ApprovalOficialMemoProcess.objects.filter(
                (Q(start_date_trip__lte=date_start) | Q(start_date_trip__lte=date_end))
                & Q(end_date_trip__gte=date_start)).exclude(cancellation=True).order_by('document__responsible')
        else:
            qs = ApprovalOficialMemoProcess.objects.filter(
                Q(person_executor__user_work_profile__job__type_of_job=self.request.user.user_work_profile.job.type_of_job)
                & (Q(start_date_trip__lte=date_start) | Q(start_date_trip__lte=date_end))
                & Q(end_date_trip__gte=date_start)).exclude(cancellation=True).order_by('document__responsible')
        dict_obj = dict()
        for item in qs.all().order_by('document__person__last_name'):
            list_obj = []
            person = FIO_format(str(item.document.person))
            # Проверяем, заполнялся ли список по сотруднику
            if person in dict_obj:
                list_obj = dict_obj[person]
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    if item.hr_accepted:
                        if item.start_date_trip <= curent_day.date() <= item.end_date_trip:
                            list_obj[days_count] = '2'
                    else:
                        if item.document.period_from <= curent_day.date() <= item.document.period_for:
                            list_obj[days_count] = '1'
                dict_obj[FIO_format(str(item.document.person))] = list_obj
            else:
                dict_obj[FIO_format(str(item.document.person))] = []
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    # print(list_obj, days_count, date_end, date_start)
                    if item.hr_accepted:
                        if item.start_date_trip <= curent_day.date() <= item.end_date_trip:
                            list_obj.append(['2', ''])
                        else:
                            list_obj.append(['0', ''])
                    else:
                        if item.document.period_from <= curent_day.date() <= item.document.period_for:
                            list_obj.append(['1', ''])
                        else:
                            list_obj.append(['0', ''])

                dict_obj[FIO_format(str(item.document.person))] = list_obj
        month_dict, year_dict = get_year_interval(2020)
        content['year_dict'] = year_dict
        content['month_dict'] = month_dict
        content['table_set'] = dict_obj
        content['table_count'] = range(1, (date_end - date_start).days + 2)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Отчет'
        content['current_year'] = current_year
        content['current_month'] = current_month

        return content


# Должностные инструкции
class DocumentsJobDescriptionList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
        Должностные инструкции - список
    """
    model = DocumentsJobDescription
    permission_required = 'hrdepartment_app.view_documentsjobdescription'

    def get_queryset(self):
        return DocumentsJobDescription.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            documents_job_list = DocumentsJobDescription.objects.all()
            data = [documents_job_item.get_data() for documents_job_item in documents_job_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Должностные инструкции'
        return context


class DocumentsJobDescriptionAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
        Должностные инструкции - создание
    """
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionAddForm
    permission_required = 'hrdepartment_app.add_documentsjobdescription'

    def get_context_data(self, **kwargs):
        content = super(DocumentsJobDescriptionAdd, self).get_context_data(**kwargs)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить должностную инструкцию'
        return content

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs


class DocumentsJobDescriptionDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
        Должностные инструкции - просмотр
    """
    model = DocumentsJobDescription
    permission_required = 'hrdepartment_app.view_documentsjobdescription'

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk).user_access.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('library_app:documents_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy('library_app:documents_list')
            return redirect(url_match)
        return super(DocumentsJobDescriptionDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class DocumentsJobDescriptionUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    """
        Должностные инструкции - редактирование
    """
    template_name = 'hrdepartment_app/documentsjobdescription_update.html'
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionUpdateForm
    permission_required = 'hrdepartment_app.change_documentsjobdescription'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs


# Приказы
class DocumentsOrderList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
        Список приказов
    """
    model = DocumentsOrder
    permission_required = 'hrdepartment_app.view_documentsorder'

    def get_queryset(self):
        return DocumentsOrder.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            documents_order_list = DocumentsOrder.objects.all().order_by("document_date").reverse()
            data = [documents_order_item.get_data() for documents_order_item in documents_order_list]
            response = {'data': data}
            # report_card_separator()
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Приказы'
        return context


class DocumentsOrderAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Добавление приказа
    """
    model = DocumentsOrder
    form_class = DocumentsOrderAddForm
    permission_required = 'hrdepartment_app.add_documentsorder'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавление приказа'
        return context

    def get(self, request, *args, **kwargs):
        document_foundation = request.GET.get('document_foundation', None)
        if document_foundation:
            memo_obj = OfficialMemo.objects.get(pk=document_foundation)
            dict_obj = {'period_from': datetime.datetime.strftime(memo_obj.period_from, '%Y-%m-%d'),
                        'period_for': datetime.datetime.strftime(memo_obj.period_for, '%Y-%m-%d'),
                        'document_date': datetime.datetime.strftime(datetime.datetime.today(), '%Y-%m-%d')}
            return JsonResponse(dict_obj, safe=False)
        document_date = request.GET.get('document_date', None)
        if document_date:
            document_date = datetime.datetime.strptime(document_date, '%Y-%m-%d')
            order_list = [item.document_number for item in
                          DocumentsOrder.objects.filter(document_date=document_date).order_by('document_date').exclude(
                              cancellation=True)]
            cancel_order = [item.document_number for item in
                            DocumentsOrder.objects.filter(Q(document_date=document_date) &
                                                          Q(cancellation=True)).order_by('document_date')]
            if len(order_list) > 0:
                if len(cancel_order) > 0:
                    result = 'Крайний: ' + str(order_list[-1]) + '; Отмененные: ' + '; '.join(cancel_order)
                else:
                    result = 'Крайний: ' + str(order_list[-1])
            else:
                result = 'За этот день нет приказов.'
            dict_obj = {'document_date': result}
            return JsonResponse(dict_obj, safe=False)

        return super().get(request, *args, **kwargs)


class DocumentsOrderDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    # Приказ - просмотр
    model = DocumentsOrder
    permission_required = 'hrdepartment_app.view_documentsorder'

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = self.get_object()
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
            # Сравниваем права доступа
            if detail_obj.access.level < user_obj.user_access.level:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('hrdepartment_app:order_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy('hrdepartment_app:order_list')
            return redirect(url_match)
        return super(DocumentsOrderDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class DocumentsOrderUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    # Приказ - изменение
    template_name = 'hrdepartment_app/documentsorder_update.html'
    model = DocumentsOrder
    form_class = DocumentsOrderUpdateForm
    permission_required = 'hrdepartment_app.change_documentsorder'

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        obj_item = self.get_object()
        kwargs = super().get_form_kwargs()
        kwargs.update({'id': obj_item.pk})
        return kwargs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context

    def get(self, request, *args, **kwargs):
        document_foundation = request.GET.get('document_foundation', None)
        if document_foundation:
            memo_obj = OfficialMemo.objects.get(pk=document_foundation)
            dict_obj = {'period_from': datetime.datetime.strftime(memo_obj.period_from, '%Y-%m-%d'),
                        'period_for': datetime.datetime.strftime(memo_obj.period_for, '%Y-%m-%d'),
                        'document_date': datetime.datetime.strftime(datetime.datetime.today(), '%Y-%m-%d')}

            return JsonResponse(dict_obj, safe=False)
        document_date = request.GET.get('document_date', None)
        if document_date:
            document_date = datetime.datetime.strptime(document_date, '%Y-%m-%d')
            order_list = [item.document_number for item in
                          DocumentsOrder.objects.filter(document_date=document_date).order_by('document_date').exclude(
                              cancellation=True)]
            cancel_order = [item.document_number for item in
                            DocumentsOrder.objects.filter(Q(document_date=document_date) &
                                                          Q(cancellation=True)).order_by('document_date')]
            if len(order_list) > 0:
                if len(cancel_order) > 0:
                    result = 'Крайний: ' + str(order_list[-1]) + '; Отмененные: ' + '; '.join(cancel_order)
                else:
                    result = 'Крайний: ' + str(order_list[-1])
            else:
                result = 'За этот день нет приказов.'
            dict_obj = {'document_date': result}
            return JsonResponse(dict_obj, safe=False)
        return super().get(request, *args, **kwargs)


class PlaceProductionActivityList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    # Места назначения - список
    model = PlaceProductionActivity
    permission_required = 'hrdepartment_app.view_placeproductionactivity'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            place_list = PlaceProductionActivity.objects.all()
            data = [place_item.get_data() for place_item in place_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Места назначения'
        return context


class PlaceProductionActivityAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    # Места назначения - создание
    model = PlaceProductionActivity
    form_class = PlaceProductionActivityAddForm
    permission_required = 'hrdepartment_app.add_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить место назначения'
        return context


class PlaceProductionActivityDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    # Места назначения - просмотр
    model = PlaceProductionActivity
    permission_required = 'hrdepartment_app.view_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class PlaceProductionActivityUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    # Места назначения - изменение
    model = PlaceProductionActivity
    template_name = 'hrdepartment_app/placeproductionactivity_form_update.html'
    form_class = PlaceProductionActivityUpdateForm
    permission_required = 'hrdepartment_app.change_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class ReportCardList(LoginRequiredMixin, ListView):
    model = ReportCard

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get('report_month')
        current_year = self.request.GET.get('report_year')
        if current_month and current_year:
            request.session['current_month'] = int(current_month)
            request.session['current_year'] = int(current_year)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session['current_month'] and request.session['current_year']:
                start_date = datetime.date(year=int(request.session['current_year']),
                                           month=int(request.session['current_month']), day=1)
                end_date = start_date + relativedelta(days=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                reportcard_list = ReportCard.objects.filter(Q(employee=self.request.user) & Q(record_type='13') & Q(
                    report_card_day__in=search_interval)).order_by('report_card_day').reverse()
            else:
                reportcard_list = ReportCard.objects.filter(
                    Q(employee=self.request.user) & Q(record_type='13')).order_by('report_card_day').reverse()
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['current_year'] = self.request.session['current_year']
        context['current_month'] = str(self.request.session['current_month'])
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком'
        return context


class ReportCardListManual(LoginRequiredMixin, ListView):
    model = ReportCard
    template_name = 'hrdepartment_app/reportcard_list_manual.html'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get('report_month')
        current_year = self.request.GET.get('report_year')
        if current_month and current_year:
            request.session['current_month'] = int(current_month)
            request.session['current_year'] = int(current_year)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session['current_month'] and request.session['current_year']:
                start_date = datetime.date(year=int(request.session['current_year']),
                                           month=int(request.session['current_month']), day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                reportcard_list = ReportCard.objects.filter(Q(record_type='13') &
                                                            Q(report_card_day__in=search_interval)).order_by(
                    'report_card_day').reverse()
            else:
                start_date = datetime.date(year=datetime.datetime.today().year,
                                           month=datetime.datetime.today().month, day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                reportcard_list = ReportCard.objects.filter(Q(record_type='13') &
                                                            Q(report_card_day__in=search_interval)).order_by(
                    'report_card_day').reverse()
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['current_year'] = self.request.session['current_year']
        context['current_month'] = str(self.request.session['current_month'])
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком'
        return context


class ReportCardListAdmin(LoginRequiredMixin, ListView):
    model = ReportCard
    template_name = 'hrdepartment_app/reportcard_list_admin.html'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        current_month = self.request.GET.get('report_month')
        current_year = self.request.GET.get('report_year')
        if current_month and current_year:
            request.session['current_month'] = int(current_month)
            request.session['current_year'] = int(current_year)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # if self.request.user.is_superuser:
            #     reportcard_list = ReportCard.objects.all()
            # else:
            #     reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            if request.session['current_month'] and request.session['current_year']:
                start_date = datetime.date(year=int(request.session['current_year']),
                                           month=int(request.session['current_month']), day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                reportcard_list = ReportCard.objects.filter(Q(report_card_day__in=search_interval)).order_by(
                    'report_card_day').reverse()
            else:
                start_date = datetime.date(year=datetime.datetime.today().year,
                                           month=datetime.datetime.today().month, day=1)
                end_date = start_date + relativedelta(day=31)
                search_interval = list(rrule.rrule(rrule.DAILY, dtstart=start_date, until=end_date))
                reportcard_list = ReportCard.objects.filter(Q(report_card_day__in=search_interval)).order_by(
                    'report_card_day').reverse()
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        month_dict, year_dict = get_year_interval(2020)
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['current_year'] = self.request.session['current_year']
        context['current_month'] = str(self.request.session['current_month'])
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком'
        return context


class ReportCardDelete(LoginRequiredMixin, DeleteView):
    model = ReportCard
    success_url = '/hr/report/admin/'


class ReportCardDetailFact(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = 'hrdepartment_app/reportcard_detail_fact.html'

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('hrdepartment_app:reportcard_detail'))

    def get_queryset(self):
        queryset = ReportCard.objects.all()
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.request.GET.get('report_month', None)
        year = self.request.GET.get('report_year', None)

        if month and year:
            current_day = datetime.datetime(int(year), int(month), 1)
        else:
            current_day = datetime.datetime.today() + relativedelta(day=1)

        first_day = current_day + relativedelta(day=1)
        last_day = current_day + relativedelta(day=31)
        # Выбираем пользователей, кто отмечался в течении интервала
        report_obj_list = ReportCard.objects.filter(
            Q(report_card_day__gte=first_day) & Q(record_type__in=['1', '13']) &
            Q(report_card_day__lte=last_day)).values('employee').order_by('employee__last_name')
        users_obj_list = []
        for item in report_obj_list:
            if item['employee'] not in users_obj_list:
                users_obj_list.append(item['employee'])
        users_obj_set = dict()
        for item in users_obj_list:
            users_obj_set[item] = DataBaseUser.objects.get(pk=item)

        month_obj = get_month(current_day)
        all_dict = dict()
        norm_time = ProductionCalendar.objects.get(calendar_month=current_day)
        # Итерируемся по списку сотрудников
        for user_obj in users_obj_set:
            data_dict, total_score, all_days_count, all_vacation_days, all_vacation_time, holiday_delta = get_working_hours(
                user_obj, current_day, state=2)
            absences = all_days_count - (norm_time.number_working_days - all_vacation_days)
            absences_delta = norm_time.get_norm_time() - (all_vacation_time + total_score) / 3600
            if absences_delta < 0:
                hour1, minute1 = divmod(total_score / 60, 60)
                time_count_hour = '{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм'.format(hour1, minute1)
            else:
                hour1, minute1 = divmod(total_score / 60, 60)
                hour2, minute2 = divmod(absences_delta * 60, 60)
                time_count_hour = '{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм<br>-{2:3.0f}&nbspч&nbsp{3:2.0f}&nbspм'.format(
                    hour1, minute1, hour2, minute2)
            all_dict[users_obj_set[user_obj]] = {
                'dict_count': data_dict,
                'days_count': all_days_count,  # days_count,
                'time_count_day': datetime.timedelta(seconds=total_score).days,
                # time_count.days, # Итого отмечено часов за месяц # Итого отмечено дней за месяц
                'time_count_hour': time_count_hour,
                # (time_count.total_seconds() / 3600),# Итого отмечено часов за месяц
                'absences': abs(absences) if absences < 0 else 0,  # Количество неявок
                'vacation_time': (all_vacation_time + total_score) / 3600,
                'holidays': norm_time.number_days_off_and_holidays - holiday_delta,
            }
        month_dict, year_dict = get_year_interval(2020)
        context['range'] = [item for item in range(1, 17)]
        context['range2'] = [item for item in range(16, 32)]
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['all_dict'] = all_dict
        context['month_obj'] = month_obj
        context['first_day'] = first_day
        context['norm_time'] = norm_time.get_norm_time()
        context['norm_day'] = norm_time.number_working_days
        context['holidays'] = norm_time.number_days_off_and_holidays
        context['last_day'] = last_day
        context['current_year'] = datetime.datetime.today().year
        context['current_month'] = str(datetime.datetime.today().month)
        context['tabel_month'] = first_day
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени (факт)'
        return context


class ReportCardDetail(LoginRequiredMixin, ListView):
    # Табель учета рабочего времени - таблица по месяцам
    model = ReportCard
    template_name = 'hrdepartment_app/reportcard_detail.html'

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('hrdepartment_app:reportcard_detail'))

    def get_queryset(self):
        queryset = ReportCard.objects.all()
        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.request.GET.get('report_month', None)
        year = self.request.GET.get('report_year', None)

        if month and year:
            current_day = datetime.datetime(int(year), int(month), 1)
        else:
            current_day = datetime.datetime.today() + relativedelta(day=1)

        first_day = current_day + relativedelta(day=1)
        last_day = current_day + relativedelta(day=31)
        # Выбираем пользователей, кто отмечался в течении интервала
        report_obj_list = ReportCard.objects.filter(
            Q(report_card_day__gte=first_day) & Q(record_type__in=['1', '13']) &
            Q(report_card_day__lte=last_day)).values('employee').order_by('employee__last_name')
        users_obj_list = []
        for item in report_obj_list:
            if item['employee'] not in users_obj_list:
                users_obj_list.append(item['employee'])
        users_obj_set = dict()
        for item in users_obj_list:
            users_obj_set[item] = DataBaseUser.objects.get(pk=item)

        month_obj = get_month(current_day)
        all_dict = dict()
        norm_time = ProductionCalendar.objects.get(calendar_month=current_day)
        # Итерируемся по списку сотрудников
        for user_obj in users_obj_set:
            data_dict, total_score, all_days_count, all_vacation_days, all_vacation_time, holiday_delta = get_working_hours(
                user_obj, current_day, state=1)
            absences = all_days_count - (norm_time.number_working_days - all_vacation_days)
            absences_delta = norm_time.get_norm_time() - (all_vacation_time + total_score) / 3600
            if absences_delta < 0:
                hour1, minute1 = divmod(total_score / 60, 60)
                time_count_hour = '{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм'.format(hour1, minute1)
            else:
                hour1, minute1 = divmod(total_score / 60, 60)
                hour2, minute2 = divmod(absences_delta * 60, 60)
                time_count_hour = '{0:3.0f}&nbspч&nbsp{1:2.0f}&nbspм<br>-{2:3.0f}&nbspч&nbsp{3:2.0f}&nbspм'.format(
                    hour1, minute1, hour2, minute2)
            all_dict[users_obj_set[user_obj]] = {
                'dict_count': data_dict,
                'days_count': all_days_count,  # days_count,
                'time_count_day': datetime.timedelta(seconds=total_score).days,
                # time_count.days, # Итого отмечено часов за месяц # Итого отмечено дней за месяц
                'time_count_hour': time_count_hour,
                # (time_count.total_seconds() / 3600),# Итого отмечено часов за месяц
                'absences': abs(absences) if absences < 0 else 0,  # Количество неявок
                'vacation_time': (all_vacation_time + total_score) / 3600,
                'holidays': norm_time.number_days_off_and_holidays - holiday_delta,
            }
        month_dict, year_dict = get_year_interval(2020)

        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['all_dict'] = all_dict
        context['month_obj'] = month_obj
        context['first_day'] = first_day
        context['norm_time'] = norm_time.get_norm_time()
        context['norm_day'] = norm_time.number_working_days
        context['holidays'] = norm_time.number_days_off_and_holidays
        context['last_day'] = last_day
        context['current_year'] = datetime.datetime.today().year
        context['current_month'] = str(datetime.datetime.today().month)
        context['tabel_month'] = first_day
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени'
        return context


class ReportCardAdd(LoginRequiredMixin, CreateView):
    model = ReportCard
    form_class = ReportCardAddForm

    def get(self, request, *args, **kwargs):
        interval = request.GET.get('interval', None)
        if interval:
            personal_start = self.request.user.user_work_profile.personal_work_schedule_start
            personal_start = datetime.timedelta(hours=personal_start.hour,
                                                minutes=personal_start.minute) - datetime.timedelta(hours=1)
            personal_end = self.request.user.user_work_profile.personal_work_schedule_end

            if datetime.datetime.strptime(interval, '%Y-%m-%d').weekday() == 4:
                personal_end = datetime.timedelta(hours=personal_end.hour, minutes=personal_end.minute)
            else:
                personal_end = datetime.timedelta(hours=personal_end.hour,
                                                  minutes=personal_end.minute) + datetime.timedelta(hours=1)
            result = [datetime.datetime.strptime(str(personal_start), '%H:%M:%S').time().strftime('%H:%M'),
                      datetime.datetime.strptime(str(personal_end), '%H:%M:%S').time().strftime('%H:%M')]
            return JsonResponse(result, safe=False)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            search_report = ReportCard.objects.filter(
                Q(employee=self.request.user) & Q(report_card_day=form.cleaned_data.get('report_card_day')) & Q(
                    record_type='1'))
            dt = form.cleaned_data.get('report_card_day')
            search_interval = list()
            start_time = list()
            end_time = list()
            for item in search_report:
                start_time.append(item.start_time.strftime("%H:%M"))
                end_time.append(item.end_time.strftime("%H:%M"))
                first_date1 = datetime.datetime(year=dt.year, month=dt.month, day=dt.day, hour=item.start_time.hour,
                                                minute=item.start_time.minute)
                first_date2 = datetime.datetime(year=dt.year, month=dt.month, day=dt.day, hour=item.end_time.hour,
                                                minute=item.end_time.minute)
                search_interval = list(rrule.rrule(rrule.MINUTELY, dtstart=first_date1, until=first_date2))
            first_date3 = datetime.datetime(year=dt.year, month=dt.month, day=dt.day,
                                            hour=form.cleaned_data.get('start_time').hour,
                                            minute=form.cleaned_data.get('start_time').minute)
            first_date4 = datetime.datetime(year=dt.year, month=dt.month, day=dt.day,
                                            hour=form.cleaned_data.get('end_time').hour,
                                            minute=form.cleaned_data.get('end_time').minute)
            interval = list(rrule.rrule(rrule.MINUTELY, dtstart=first_date3, until=first_date4))
            set1 = set(search_interval)
            set2 = set(interval)
            result = set2.intersection(set1)
            if len(result) > 0:
                form.add_error('start_time',
                               f'Ошибка! Вы указали время с {form.cleaned_data.get("start_time").strftime("%H:%M")} по {form.cleaned_data.get("end_time").strftime("%H:%M")}, но на заданную дату По TimeControl у вас имеется интервал с {start_time} по {end_time}')
                return super().form_invalid(form)

            refresh_form = form.save(commit=False)
            refresh_form.employee = self.request.user
            refresh_form.record_type = '13'
            refresh_form.manual_input = True

            refresh_form.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('customers_app:profile', args=(self.request.user.pk,))


class ReportCardUpdate(LoginRequiredMixin, UpdateView):
    model = ReportCard
    form_class = ReportCardUpdateForm
    template_name = 'hrdepartment_app/reportcard_form_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_obj = self.get_object()
        if self.request.user.is_superuser:
            context['min'] = datetime.datetime(1, 1, 1, 1, 0).strftime('%H:%M')
            context['max'] = datetime.datetime(1, 1, 1, 23, 0).strftime('%H:%M')
        else:
            context['min'] = user_obj.employee.user_work_profile.personal_work_schedule_start.strftime('%H:%M')
            context['max'] = user_obj.employee.user_work_profile.personal_work_schedule_end.strftime('%H:%M')
        return context

    def get(self, request, *args, **kwargs):
        interval = request.GET.get('interval', None)
        if interval:
            personal_start = self.request.user.user_work_profile.personal_work_schedule_start
            personal_start = datetime.timedelta(hours=personal_start.hour,
                                                minutes=personal_start.minute) - datetime.timedelta(hours=1)
            personal_end = self.request.user.user_work_profile.personal_work_schedule_end

            if datetime.datetime.strptime(interval, '%Y-%m-%d').weekday() == 4:
                personal_end = datetime.timedelta(hours=personal_end.hour, minutes=personal_end.minute)
            else:
                personal_end = datetime.timedelta(hours=personal_end.hour,
                                                  minutes=personal_end.minute) + datetime.timedelta(hours=1)
            result = [datetime.datetime.strptime(str(personal_start), '%H:%M:%S').time().strftime('%H:%M'),
                      datetime.datetime.strptime(str(personal_end), '%H:%M:%S').time().strftime('%H:%M')]
            return JsonResponse(result, safe=False)
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('hrdepartment_app:reportcard_list')

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs


# Положения
class ProvisionsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
        Должностные инструкции - список
    """
    model = Provisions
    permission_required = 'hrdepartment_app.view_provisions'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            provisions_list = Provisions.objects.all()
            data = [provisions_item.get_data() for provisions_item in provisions_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Положения'
        return context


class ProvisionsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
        Положения - создание
    """
    model = Provisions
    form_class = ProvisionsAddForm
    permission_required = 'hrdepartment_app.add_provisions'

    def get_context_data(self, **kwargs):
        content = super(ProvisionsAdd, self).get_context_data(**kwargs)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить положение'
        return content

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs


class ProvisionsDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
        Положения - просмотр
    """
    model = Provisions
    permission_required = 'hrdepartment_app.view_provisions'

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk).user_access.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('hrdepartment_app:provisions_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy('hrdepartment_app:provisions_list')
            return redirect(url_match)
        return super(ProvisionsDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class ProvisionsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    """
        Положения - редактирование
    """
    template_name = 'hrdepartment_app/provisions_form_update.html'
    model = Provisions
    form_class = ProvisionsUpdateForm
    permission_required = 'hrdepartment_app.change_provisions'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs
