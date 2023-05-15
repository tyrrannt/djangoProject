import datetime
from calendar import monthrange

from dateutil.relativedelta import relativedelta
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from loguru import logger

from administration_app.models import PortalProperty
from administration_app.utils import change_session_context, change_session_queryset, change_session_get, FIO_format, \
    get_jsons_data, ending_day, get_history
from customers_app.models import DataBaseUser, Counteragent
from hrdepartment_app.forms import MedicalExaminationAddForm, MedicalExaminationUpdateForm, OfficialMemoUpdateForm, \
    OfficialMemoAddForm, ApprovalOficialMemoProcessAddForm, ApprovalOficialMemoProcessUpdateForm, \
    BusinessProcessDirectionAddForm, BusinessProcessDirectionUpdateForm, MedicalOrganisationAddForm, \
    MedicalOrganisationUpdateForm, PurposeAddForm, PurposeUpdateForm, DocumentsOrderUpdateForm, DocumentsOrderAddForm, \
    DocumentsJobDescriptionUpdateForm, DocumentsJobDescriptionAddForm, PlaceProductionActivityAddForm, \
    PlaceProductionActivityUpdateForm, ApprovalOficialMemoProcessChangeForm
from hrdepartment_app.hrdepartment_util import get_medical_documents, send_mail_change
from hrdepartment_app.models import Medical, OfficialMemo, ApprovalOficialMemoProcess, BusinessProcessDirection, \
    MedicalOrganisation, Purpose, DocumentsJobDescription, DocumentsOrder, PlaceProductionActivity, ReportCard

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# Create your views here.
class MedicalOrganisationList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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


class MedicalOrganisationAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationAddForm
    permission_required = 'customers_app.add_medicalorganisation'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить медицинскую организацию'
        return context


class MedicalOrganisationUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationUpdateForm
    permission_required = 'customers_app.change_medicalorganisation'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class MedicalExamination(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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
            medical_list = Medical.objects.all()
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


class MedicalExaminationAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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


class MedicalExaminationUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
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


class OfficialMemoList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = OfficialMemo
    paginate_by = 6
    permission_required = 'hrdepartment_app.view_officialmemo'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if request.user.is_superuser or request.user.user_work_profile.job.type_of_job == '0':
                memo_list = OfficialMemo.objects.all()
            else:
                memo_list = OfficialMemo.objects.filter(
                    responsible__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job)

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


class OfficialMemoAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
        if memo_type and employee:
            if memo_type == '2':
                memo_list = OfficialMemo.objects.filter(person=employee).exclude(cancellation=True)
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                return JsonResponse(memo_obj_list)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, '%Y-%m-%d')
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date))
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
        return super(OfficialMemoAdd, self).get(request, *args, **kwargs)


class OfficialMemoDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = OfficialMemo
    permission_required = 'hrdepartment_app.view_officialmemo'

    def get_context_data(self, **kwargs):
        content = super().get_context_data(**kwargs)
        content['change_history'] = get_history(self, OfficialMemo)
        return content


class OfficialMemoUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    template_name = 'hrdepartment_app/officialmemo_form_update.html'
    permission_required = 'hrdepartment_app.change_officialmemo'

    def get_context_data(self, **kwargs):

        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        # Получаем объект
        # Получаем разницу в днях, для определения количества дней СП
        delta = (self.object.period_for - self.object.period_from)
        # Передаем количество дней в контекст
        content['period'] = int(delta.days) + 1
        # Получаем все служебные записки по человеку, исключая текущую
        filters = OfficialMemo.objects.filter(person=self.object.person).exclude(pk=self.object.pk)
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
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.object}'
        content['change_history'] = get_history(self, OfficialMemo)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)

    def form_valid(self, form):
        critical_change = 0

        def person_finder(object_item, item, instanse_obj):
            person_list = ['Сотрудник']
            if object_item._meta.get_field(k).verbose_name in person_list:
                return DataBaseUser.objects.get(pk=instanse_obj[item])
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
            message = '<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:\n'
            if place_old != place_new:
                critical_change = 1
                message += f'Место назначения: <strike>{place_old}</strike> -> {place_new}\n'
                changed = True
            for k in diffkeys:
                if k != '_state':
                    if object_item._meta.get_field(k).verbose_name == 'Сотрудник':
                        critical_change = 1
                    if object_item._meta.get_field(k).verbose_name == 'Дата начала':
                        if new_instance[k] < old_instance[k]:
                            critical_change = 1
                    message += f'{object_item._meta.get_field(k).verbose_name}: <strike>{person_finder(object_item, k, old_instance)}</strike> -> {person_finder(object_item, k, new_instance)}\n'
                    changed = True

            if changed:
                object_item.history_change.create(author=self.request.user, body=message)
            if critical_change == 1:
                get_obj = self.get_object()
                try:
                    get_bpmemo_obj = ApprovalOficialMemoProcess.objects.get(pk=object_item.docs.pk)
                    if object_item.order:
                        get_order_obj = object_item.order
                    else:
                        get_order_obj = ''
                    if get_order_obj != '':
                        # ToDo: Сделать обработку отправки письма
                        send_mail_change(1, get_obj)
                        get_bpmemo_obj.location_selected = False
                        get_bpmemo_obj.process_accepted = False
                        get_bpmemo_obj.email_send = False
                        get_bpmemo_obj.accommodation = ''
                        get_bpmemo_obj.order = None
                        get_order_obj.cancellation = True
                        get_obj.accommodation = ''
                        get_obj.document_accepted = False
                        get_obj.order = None
                        get_obj.comments = 'Документ согласован'
                        get_obj.save()
                        get_bpmemo_obj.save()
                        get_order_obj.save()
                    else:
                        # ToDo: Сделать обработку отправки письма
                        send_mail_change(2, get_obj)
                        get_bpmemo_obj.location_selected = False
                        get_bpmemo_obj.accommodation = ''
                        get_obj.comments = 'Документ согласован'
                        get_obj.save()
                        get_bpmemo_obj.save()
                except Exception as _ex:
                    print(_ex)
            return HttpResponseRedirect(reverse('hrdepartment_app:memo_list'))

        else:
            logger.info(f'{form.errors}')

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
        memo_type = request.GET.get('memo_type', None)
        if memo_type and employee:
            if memo_type == '2':
                memo_list = OfficialMemo.objects.filter(person=employee).exclude(pk=self.get_object().pk)
                memo_obj_list = dict()
                for item in memo_list:
                    memo_obj_list.update({item.get_title(): item.pk})
                return JsonResponse(memo_obj_list)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, '%Y-%m-%d')
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_for__gte=check_date))
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
            print(period_for_value, dict_obj)
            return JsonResponse(dict_obj, safe=False)
        return super(OfficialMemoUpdate, self).get(request, *args, **kwargs)


class ApprovalOficialMemoProcessList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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
                approvalmemo_list = ApprovalOficialMemoProcess.objects.all()
            else:
                approvalmemo_list = ApprovalOficialMemoProcess.objects.filter(
                    person_executor__user_work_profile__job__type_of_job=request.user.user_work_profile.job.type_of_job)
            data = [approvalmemo_item.get_data() for approvalmemo_item in approvalmemo_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // БП по служебным поездкам'
        return context


class ApprovalOficialMemoProcessAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm
    permission_required = 'hrdepartment_app.add_approvaloficialmemoprocess'

    def get_context_data(self, **kwargs):
        global person_agreement_list
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)
        content['form'].fields['document'].queryset = OfficialMemo.objects.filter(
            Q(docs__isnull=True) & Q(responsible=self.request.user))
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


class ApprovalOficialMemoProcessUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
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
        if document.document.official_memo_type == '1':
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.pk).exclude(cancellation=True)
        elif document.document.official_memo_type == '2':
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(
                document_foundation__pk=document.document.document_extension.pk).exclude(cancellation=True)
        else:
            content['form'].fields['order'].queryset = DocumentsOrder.objects.filter(pk=0)
        delta = document.document.period_for - document.document.period_from
        content['ending_day'] = ending_day(int(delta.days) + 1)
        content['change_history'] = get_history(self, ApprovalOficialMemoProcess)
        content['without_departure'] = False if document.document.official_memo_type == '3' else True
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
            # в old_instance сохраняем старые значения записи
            object_item = self.get_object()
            old_instance = object_item.__dict__
            form.save()
            object_item = self.get_object()
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
        if request.POST.get('submit_for_approval'):
            document.comments = 'Передан на согласование'
            change_status = 1
        else:
            document.comments = 'Документооборот начат'
            change_status = 1
        if request.POST.get('document_not_agreed'):
            document.comments = 'Документ согласован'
            change_status = 1
        if request.POST.get('location_selected'):
            document.comments = 'Утверждено место проживания'
            change_status = 1
        if request.POST.get('process_accepted'):
            document.comments = 'Создан приказ'
            change_status = 1
        if request.POST.get('originals_received') and request.POST.get('date_receipt_original'):
            document.comments = 'Получены оригиналы'
            change_status = 1
        if request.POST.get('originals_received') and request.POST.get('date_transfer_hr'):
            document.comments = 'Передано в ОК'
            change_status = 1
        if request.POST.get('hr_accepted'):
            document.comments = 'Передано в бухгалтерию'
            change_status = 1
        else:
            document.document_accepted = False
            change_status = 1
        if request.POST.get('accepted_accounting'):
            document.comments = 'Документооборот завершен'
            document.document_accepted = True
            change_status = 1

        if change_status > 0:
            if document.cancellation:
                document.comments = 'Документ отменен'
            document.save()
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')


class ApprovalOficialMemoProcessCancel(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessChangeForm
    template_name = 'hrdepartment_app/approvaloficialmemoprocess_form_cancel.html'

    def form_valid(self, form):
        if form.is_valid():
            obj_item = self.get_object()
            official_memo = obj_item.document
            order = obj_item.order
            form.save()
            if official_memo:
                official_memo.cancellation = True
                official_memo.reason_cancellation = obj_item.reason_cancellation
                official_memo.comments = 'Документ отменен'
                official_memo.save()
            if order:
                order.cancellation = True
                order.reason_cancellation = obj_item.reason_cancellation
                order.save()

            obj_item.send_mail(title='Уведомление об отмене')
        return super().form_valid(form)


class PurposeList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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


class PurposeAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Purpose
    form_class = PurposeAddForm
    permission_required = 'hrdepartment_app.add_purpose'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить цель СП'
        return context


class PurposeUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Purpose
    form_class = PurposeUpdateForm
    permission_required = 'hrdepartment_app.change_purpose'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class BusinessProcessDirectionList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = BusinessProcessDirection
    permission_required = 'hrdepartment_app.view_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Направление бизнес-процессов'
        return context


class BusinessProcessDirectionAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionAddForm
    permission_required = 'hrdepartment_app.add_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить направление БП'
        return context


class BusinessProcessDirectionUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionUpdateForm
    permission_required = 'hrdepartment_app.change_businessprocessdirection'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class ReportApprovalOficialMemoProcessList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess
    template_name = 'hrdepartment_app/reportapprovaloficialmemoprocess_list.html'
    permission_required = 'hrdepartment_app.view_approvaloficialmemoprocess'

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('hrdepartment_app:bpmemo_report'))

    def get_queryset(self):
        qs = super(ReportApprovalOficialMemoProcessList, self).get_queryset()
        # date_start = datetime.datetime.strptime('2023-02-01', '%Y-%m-%d')
        # date_end = datetime.datetime.strptime('2023-02-28', '%Y-%m-%d')
        # qs = ApprovalOficialMemoProcess.objects.filter(Q(person_executor__pk=self.request.user.pk) &
        #                                                (Q(document__period_from__lte=date_start) | Q(
        #                                                    document__period_for__gte=date_start)) &
        #                                                (Q(document__period_from__lte=date_end) | Q(
        #                                                    document__period_for__gte=date_end))
        #                                                ).order_by('document__period_from')

        return qs

    def get(self, request, *args, **kwargs):
        # Получаем выборку из базы данных, если был изменен один из параметров
        if self.request.GET:
            current_year = int(self.request.GET.get('CY'))
            current_month = int(self.request.GET.get('CM'))
            html_obj = ''
            from calendar import monthrange
            days = monthrange(current_year, current_month)[1]
            date_start = datetime.datetime.strptime(f'{current_year}-{current_month}-01', '%Y-%m-%d')
            date_end = datetime.datetime.strptime(f'{current_year}-{current_month}-{days}', '%Y-%m-%d')
            qs = ApprovalOficialMemoProcess.objects.filter(
                Q(person_executor__user_work_profile__job__type_of_job=self.request.user.user_work_profile.job.type_of_job)
                & (Q(document__period_from__lte=date_start) | Q(document__period_from__lte=date_end))
                & Q(document__period_for__gte=date_start)).order_by('document__period_from')
            dict_obj = dict()
            for item in qs.all():
                list_obj = []
                person = FIO_format(str(item.document.person))
                place = '; '.join([item.name for item in item.document.place_production_activity.all()])
                place_short = '; '.join([item.short_name for item in item.document.place_production_activity.all()])
                if person in dict_obj:
                    list_obj = dict_obj[person]
                    for days_count in range(0, (date_end - date_start).days + 1):
                        curent_day = date_start + datetime.timedelta(days_count)
                        if item.document.period_from <= curent_day.date() <= item.document.period_for:
                            list_obj[days_count] = ['1', place, place_short]
                    dict_obj[FIO_format(str(item.document.person))] = list_obj
                else:
                    dict_obj[FIO_format(str(item.document.person))] = []
                    for days_count in range(0, (date_end - date_start).days + 1):
                        curent_day = date_start + datetime.timedelta(days_count)
                        if item.document.period_from <= curent_day.date() <= item.document.period_for:
                            list_obj.append(['1', place, place_short])
                        else:
                            list_obj.append(['0', ''])
                    dict_obj[FIO_format(str(item.document.person))] = list_obj

                table_set = dict_obj
                html_table_count = ''
                table_count = range(1, (date_end - date_start).days + 2)
                for item in table_count:
                    html_table_count += f'<th width="2%"><span style="color: #0a53be">{item}</span></th>'
                html_table_set = ''
                for key, value in table_set.items():
                    html_table_set += f'<tr><td width="14%"><strong>{key}</strong></td>'
                    for unit in value:
                        if unit[0] == '1':
                            place = unit[1].replace('"', "")
                            plase_short = ''  # unit[2]
                            html_table_set += f'<td width="2%" style="background-color: #d2691e"  title="{place}">{plase_short}</td>'
                        else:
                            html_table_set += '<td width="2%" style="background-color: #f5f5dc"></td>'
                    html_table_set += '</tr>'

                html_obj = f'''<table class="table table-ecommerce-simple table-striped mb-0" id="id_datatable" style="min-width: 1000px;">
                                <thead>
                                <tr>
                                    <th width="14%"><span style="color: #0a53be">ФИО</span></th>
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
        qs = ApprovalOficialMemoProcess.objects.filter(Q(person_executor__pk=self.request.user.pk) & (
                Q(document__period_from__lte=date_start) | Q(document__period_from__lte=date_end)) & Q(
            document__period_for__gte=date_start)).order_by('document__period_from')
        dict_obj = dict()
        for item in qs.all():
            list_obj = []
            person = FIO_format(str(item.document.person))
            if person in dict_obj:
                list_obj = dict_obj[person]
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    if item.document.period_from <= curent_day.date() <= item.document.period_for:
                        list_obj[days_count] = '1'
                dict_obj[FIO_format(str(item.document.person))] = list_obj
            else:
                dict_obj[FIO_format(str(item.document.person))] = []
                for days_count in range(0, (date_end - date_start).days + 1):
                    curent_day = date_start + datetime.timedelta(days_count)
                    if item.document.period_from <= curent_day.date() <= item.document.period_for:
                        list_obj.append('1')
                    else:
                        list_obj.append('0')
                dict_obj[FIO_format(str(item.document.person))] = list_obj

        content['table_set'] = dict_obj
        content['table_count'] = range(1, (date_end - date_start).days + 2)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Отчет'
        content['current_year'] = current_year
        content['current_month'] = current_month

        return content


# Должностные инструкции
class DocumentsJobDescriptionList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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


class DocumentsJobDescriptionAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionAddForm
    permission_required = 'hrdepartment_app.add_documentsjobdescription'

    def get_context_data(self, **kwargs):
        content = super(DocumentsJobDescriptionAdd, self).get_context_data(**kwargs)
        content['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить должностную инструкцию'
        return content


class DocumentsJobDescriptionDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = DocumentsJobDescription
    permission_required = 'hrdepartment_app.view_documentsjobdescription'

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk).access_level.documents_access_view.level
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


class DocumentsJobDescriptionUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = 'hrdepartment_app/documentsjobdescription_update.html'
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionUpdateForm
    permission_required = 'hrdepartment_app.change_documentsjobdescription'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


# Приказы
class DocumentsOrderList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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
            documents_order_list = DocumentsOrder.objects.all().order_by('pk').reverse()
            data = [documents_order_item.get_data() for documents_order_item in documents_order_list]
            response = {'data': data}
            # report_card_separator()
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Приказы'
        return context


class DocumentsOrderAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
        return super().get(request, *args, **kwargs)


class DocumentsOrderDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
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


class DocumentsOrderUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = 'hrdepartment_app/documentsorder_update.html'
    model = DocumentsOrder
    form_class = DocumentsOrderUpdateForm
    permission_required = 'hrdepartment_app.change_documentsorder'

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
        return super().get(request, *args, **kwargs)


class PlaceProductionActivityList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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


class PlaceProductionActivityAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PlaceProductionActivity
    form_class = PlaceProductionActivityAddForm
    permission_required = 'hrdepartment_app.add_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить место назначения'
        return context


class PlaceProductionActivityDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PlaceProductionActivity
    permission_required = 'hrdepartment_app.view_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class PlaceProductionActivityUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = PlaceProductionActivity
    template_name = 'hrdepartment_app/placeproductionactivity_form_update.html'
    form_class = PlaceProductionActivityUpdateForm
    permission_required = 'hrdepartment_app.change_placeproductionactivity'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


class ReportCardList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ReportCard
    permission_required = 'hrdepartment_app.view_reportcard'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if self.request.user.is_superuser:
                reportcard_list = ReportCard.objects.all()
            else:
                reportcard_list = ReportCard.objects.filter(employee=self.request.user).select_related('employee')
            data = [reportcard_item.get_data() for reportcard_item in reportcard_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени списком'
        return context


class ReportCardDetail(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ReportCard
    permission_required = 'hrdepartment_app.view_reportcard'
    template_name = 'hrdepartment_app/reportcard_detail.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        sample_date = datetime.datetime(2023, 2, 14)
        # first_day = sample_date + relativedelta(day=1)
        # last_day = sample_date + relativedelta(day=31)
        first_day = datetime.datetime.today() + relativedelta(day=1)
        last_day = datetime.datetime.today() + relativedelta(day=31)
        total_score = 0
        data_dict = dict()
        for item in ReportCard.objects.filter(Q(report_card_day__gte=first_day) & Q(report_card_day__lte=last_day) & Q(employee=self.request.user)):
            if data_dict.get(str(item.employee)):
                time_1 = datetime.timedelta(hours=item.start_time.hour, minutes=item.start_time.minute)
                time_2 = datetime.timedelta(hours=item.end_time.hour, minutes=item.end_time.minute)
                time_3 = datetime.timedelta(hours=8, minutes=30) if item.report_card_day.weekday() != 5 else datetime.timedelta(hours=7, minutes=30)
                time_4 = (time_2.total_seconds() - time_1.total_seconds()) - time_3.total_seconds()
                total_score += time_4
                sign = '-' if time_4 < 0 else ''
                time_delta = datetime.timedelta(seconds=abs(time_4))
                data_dict[str(item.employee)].append(
                    [item.report_card_day, item.start_time, item.end_time, sign, time_delta])


            else:
                data_dict[str(item.employee)] = []
                time_1 = datetime.timedelta(hours=item.start_time.hour, minutes=item.start_time.minute)
                time_2 = datetime.timedelta(hours=item.end_time.hour, minutes=item.end_time.minute)
                time_3 = datetime.timedelta(hours=8, minutes=30) if item.report_card_day.weekday() != 5 else datetime.timedelta(hours=7, minutes=30)
                time_4 = (time_2.total_seconds() - time_1.total_seconds()) - time_3.total_seconds()
                total_score += time_4
                sign = '-' if time_4 < 0 else ''
                time_delta = datetime.timedelta(seconds=abs(time_4))
                data_dict[str(item.employee)].append(
                    [item.report_card_day, item.start_time, item.end_time, sign, time_delta])

        print(data_dict)
        context['data_dict'] = data_dict
        context['first_day'] = first_day
        context['last_day'] = last_day
        context['total_sign'] = '-' if total_score < 0 else ''
        context['total_score'] = datetime.timedelta(seconds=abs(total_score))
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Табель учета рабочего времени'
        return context
