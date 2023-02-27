import datetime
import json
from calendar import monthrange

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView
from loguru import logger

from administration_app.utils import change_session_context, change_session_queryset, change_session_get, FIO_format, \
    get_jsons_data
from customers_app.models import DataBaseUser, Counteragent, Division, Job, HarmfulWorkingConditions
from hrdepartment_app.forms import MedicalExaminationAddForm, MedicalExaminationUpdateForm, OfficialMemoUpdateForm, \
    OfficialMemoAddForm, ApprovalOficialMemoProcessAddForm, ApprovalOficialMemoProcessUpdateForm, \
    BusinessProcessDirectionAddForm, BusinessProcessDirectionUpdateForm, MedicalOrganisationAddForm, \
    MedicalOrganisationUpdateForm
from hrdepartment_app.models import Medical, OfficialMemo, ApprovalOficialMemoProcess, BusinessProcessDirection, \
    MedicalOrganisation

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip", serialize=True)

# Create your views here.
class MedicalOrganisationList(LoginRequiredMixin, ListView):
    model = MedicalOrganisation

    def get(self, request, *args, **kwargs):
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


class MedicalOrganisationAdd(LoginRequiredMixin, CreateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationAddForm


class MedicalOrganisationUpdate(LoginRequiredMixin, UpdateView):
    model = MedicalOrganisation
    form_class = MedicalOrganisationUpdateForm


class MedicalExamination(LoginRequiredMixin, ListView):
    model = Medical
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by('pk').reverse()
        return qs

    def get(self, request, *args, **kwargs):
        count = 0
        type_of = [
            ('1', 'Поступающий на работу'),
            ('2', 'Работающий')
        ]

        type_of_inspection = [
            ('1', 'Медицинский осмотр'),
            ('2', 'Психиатрическое освидетельствование')
        ]

        type_inspection = [
            ('1', 'Предварительный'),
            ('2', 'Периодический'),
            ('3', 'Внеплановый')
        ]
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Document", "НаправлениеНаМедицинскийОсмотр", 0)
            # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Posted']:
                    db_user = DataBaseUser.objects.filter(person_ref_key=item['ФизическоеЛицо_Key'])
                    db_med_org = item['МедицинскаяОрганизация_Key']
                    if db_user.count() > 0 and db_med_org != '00000000-0000-0000-0000-000000000000':
                        qs = list()
                        for items in item['ВредныеФакторыИВидыРабот']:
                            qs.append(HarmfulWorkingConditions.objects.get(ref_key=items['ВредныйФактор_Key']))
                        divisions_kwargs = {
                            'ref_key': item['Ref_Key'],
                            'number': item['Number'],
                            'person': DataBaseUser.objects.get(person_ref_key=item['ФизическоеЛицо_Key']),
                            'date_entry': datetime.datetime.strptime(item['Date'][:10], "%Y-%m-%d"),
                            'date_of_inspection': datetime.datetime.strptime(item['ДатаОсмотра'][:10], "%Y-%m-%d"),
                            'organisation': MedicalOrganisation.objects.get(ref_key=item['МедицинскаяОрганизация_Key']),
                            'working_status': 1 if next(
                                x[0] for x in type_inspection if x[1] == item['ТипОсмотра']) == 1 else 2,
                            'view_inspection': 1 if item['ВидОсмотра'] == 'МедицинскийОсмотр' else 2,
                            'type_inspection': next(x[0] for x in type_inspection if x[1] == item['ТипОсмотра']),
                            # 'harmful': qs,
                        }
                        Medical.objects.update_or_create(ref_key=item['Ref_Key'], defaults=divisions_kwargs)
                        db_instance = Medical.objects.get(ref_key=item['Ref_Key'])
                        if len(qs) > 0:
                            for units in qs:
                                db_instance.harmful.add(units)
                        db_instance.save()
                        count += 1

            url_match = reverse_lazy('hrdepartment_app:medical_list')
            return redirect(url_match)
        change_session_get(self.request, self)
        return super(MedicalExamination, self).get(request, *args, **kwargs)


class MedicalExaminationAdd(LoginRequiredMixin, CreateView):
    model = Medical
    form_class = MedicalExaminationAddForm

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationAdd, self).get_context_data(**kwargs)
        content['all_person'] = DataBaseUser.objects.filter(type_users='staff_member')
        content['all_contragent'] = Counteragent.objects.all()
        content['all_status'] = Medical.type_of
        content['all_harmful'] = ''
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class MedicalExaminationUpdate(LoginRequiredMixin, UpdateView):
    model = Medical
    form_class = MedicalExaminationUpdateForm
    template_name = 'hrdepartment_app/medical_form_update.html'

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationUpdate, self).get_context_data(**kwargs)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')


class OfficialMemoList(LoginRequiredMixin, ListView):
    model = OfficialMemo
    paginate_by = 6

    def get(self, request, *args, **kwargs):
        change_session_get(self.request, self)
        return super(OfficialMemoList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(OfficialMemoList, self).get_queryset().order_by('pk')
        change_session_queryset(self.request, self)
        if not self.request.user.is_superuser:
            user_division = DataBaseUser.objects.get(pk=self.request.user.pk).user_work_profile.divisions
            qs = OfficialMemo.objects.filter(responsible__user_work_profile__divisions=user_division).order_by(
                'pk').reverse()
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(OfficialMemoList, self).get_context_data(**kwargs)
        context['title'] = 'Список пользователей'
        change_session_context(context, self)
        return context


class OfficialMemoAdd(LoginRequiredMixin, CreateView):
    model = OfficialMemo
    form_class = OfficialMemoAddForm

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoAdd, self).get_context_data(**kwargs)
        # content['all_status'] = OfficialMemo.type_of_accommodation
        # Генерируем список сотрудников, которые на текущий момент времени не находятся в СП
        users_list = [person.person_id for person in OfficialMemo.objects.filter(
            Q(period_from__lte=datetime.datetime.today()) & Q(period_for__gte=datetime.datetime.today()))]
        # Выбераем из базы тех сотрудников, которые содержатся в списке users_list и исключаем из него суперпользователя
        # content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(pk__in=users_list).exclude(is_superuser=True)
        content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(is_superuser=True)
        content['form'].fields['place_production_activity'].queryset = Division.objects.all().exclude(
            destination_point=False)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_valid(self, form):
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
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
                logger.info(f'За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}')
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


class OfficialMemoUpdate(LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    template_name = 'hrdepartment_app/officialmemo_form_update.html'

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        # Получаем объект
        period = self.get_object()
        # Получаем разницу в днях, для определения количества дней СП
        delta = (period.period_for - period.period_from)
        # Передаем количество дней в контекст
        content['period'] = int(delta.days) + 1
        # Получаем все служебные записки по человеку, исключая текущую
        filters = OfficialMemo.objects.filter(person=period.person).exclude(pk=period.pk)
        filter_string = {
            "pk": 0,
            "period": datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()
        }
        # Проходимся по выборке в цикле
        for item in filters:
            if item.period_for > filter_string["period"]:
                filter_string["pk"] = item.pk
                filter_string["period"] = item.period_for

        content['form'].fields['place_production_activity'].queryset = Division.objects.all().exclude(
            destination_point=False)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)

    def form_valid(self, form):
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        global filter_string
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
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
                logger.info(f'За заданный период СП не найдены. Пользователь {self.request.user.username}, {AttributeError}')
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
            print(interval)
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
                period_for_value = max_date
                dict_obj['pfv'] = max_date
            else:
                dict_obj['pfv'] = period_for_value
            return JsonResponse(dict_obj, safe=False)
        return super(OfficialMemoUpdate, self).get(request, *args, **kwargs)


class ApprovalOficialMemoProcessList(LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess

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


class ApprovalOficialMemoProcessAdd(LoginRequiredMixin, CreateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm

    def get_context_data(self, **kwargs):
        global person_agreement_list
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)
        content['form'].fields['document'].queryset = OfficialMemo.objects.filter(docs__isnull=True)
        business_process = BusinessProcessDirection.objects.all()
        users_list = DataBaseUser.objects.all()
        #
        content['form'].fields['person_executor'].queryset = users_list.filter(
            pk=self.request.user.pk)

        person_agreement_list = list()
        content['form'].fields['person_agreement'].queryset = users_list.filter(
            user_work_profile__job__pk__in=person_agreement_list)
        for item in business_process:
            if item.person_executor.filter(name__contains=self.request.user.user_work_profile.job.name):
                person_agreement_list = [items[0] for items in item.person_agreement.values_list()]
                content['form'].fields['person_agreement'].queryset = users_list.filter(
                    user_work_profile__job__pk__in=person_agreement_list)
        content['form'].fields['person_distributor'].queryset = DataBaseUser.objects.filter(
            Q(user_work_profile__divisions__type_of_role='1') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        content['form'].fields['person_department_staff'].queryset = DataBaseUser.objects.filter(
            Q(user_work_profile__divisions__type_of_role='2') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')


class ApprovalOficialMemoProcessUpdate(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessUpdateForm
    template_name = 'hrdepartment_app/approvaloficialmemoprocess_form_update.html'

    def get_context_data(self, **kwargs):
        global person_agreement_list
        business_process = BusinessProcessDirection.objects.all()
        users_list = DataBaseUser.objects.all()
        content = super(ApprovalOficialMemoProcessUpdate, self).get_context_data(**kwargs)
        document = self.get_object()
        content['document'] = document.document
        # Получаем подразделение исполнителя
        # division = document.person_executor.user_work_profile.divisions
        # При редактировании БП фильтруем поле исполнителя, чтоб нельзя было изменить его в процессе работы
        content['form'].fields['person_executor'].queryset = users_list.filter(pk=document.person_executor.pk)
        # Если установлен признак согласования документа, то фильтруем поле согласующего лица
        if document.document_not_agreed:
            content['form'].fields['person_agreement'].queryset = users_list.filter(
                pk=document.person_agreement.pk)
        else:
            # Иначе по подразделению исполнителя фильтруем руководителей для согласования
            person_agreement_list = list()
            content['form'].fields['person_agreement'].queryset = users_list.filter(
                user_work_profile__job__pk__in=person_agreement_list)
            for item in business_process:
                if item.person_executor.filter(name__contains=self.request.user.user_work_profile.job.name):
                    person_agreement_list = [items[0] for items in item.person_agreement.values_list()]
                    content['form'].fields['person_agreement'].queryset = users_list.filter(
                        user_work_profile__job__pk__in=person_agreement_list)
        content['form'].fields['person_distributor'].queryset = users_list.filter(
            Q(user_work_profile__divisions__type_of_role='1') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        content['form'].fields['person_department_staff'].queryset = users_list.filter(
            Q(user_work_profile__divisions__type_of_role='2') & Q(user_work_profile__job__right_to_approval=True) &
            Q(is_superuser=False))
        try:
            check = users_list.get(pk=document.person_distributor.pk)
        except Exception as _ex:
            print('345435345345435')

        return content

    def form_valid(self, form):
        return super().form_valid(form)

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
        data = request.POST.get('order_date')
        number = request.POST.get('order_number')
        accommodation = request.POST.get('accommodation')
        change_status = 0
        document = OfficialMemo.objects.get(pk=self.get_object().document.pk)
        if document.order_date != data:
            # Если добавлена или изменена дата приказа, сохраняем ее в документ Служебной записки
            if data != '':
                document.order_date = data
                change_status = 1
        if document.order_number != number:
            # Если добавлен или изменен номер приказа, сохраняем его в документ Служебной записки
            document.order_number = number
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
            document.comments = 'Документооборот завершен'
            document.document_accepted = True
            change_status = 1
        else:
            document.document_accepted = False
            change_status = 1
        if change_status > 0:
            document.save()
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')


class BusinessProcessDirectionList(LoginRequiredMixin, ListView):
    model = BusinessProcessDirection


class BusinessProcessDirectionAdd(LoginRequiredMixin, CreateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionAddForm


class BusinessProcessDirectionUpdate(LoginRequiredMixin, UpdateView):
    model = BusinessProcessDirection
    form_class = BusinessProcessDirectionUpdateForm


class ReportApprovalOficialMemoProcessList(LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess
    template_name = 'hrdepartment_app/reportapprovaloficialmemoprocess_list.html'

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

                table_set = dict_obj
                html_table_count = ''
                table_count = range(1, (date_end - date_start).days + 2)
                for item in table_count:
                    html_table_count += f'<th width="2%"><span style="color: #0a53be">{item}</span></th>'
                html_table_set = ''
                for key, value in table_set.items():
                    html_table_set += f'<tr><td width="14%"><strong>{key}</strong></td>'
                    for unit in value:
                        if unit == '1':
                            html_table_set += '<td width="2%" style="background-color: #d2691e"></td>'
                        else:
                            html_table_set += '<td width="2%" style="background-color: #f5f5dc"></td>'
                    html_table_set += '</tr>'

                html_obj = f'''<table class="table table-ecommerce-simple table-striped mb-0" id="id_datatable" style="min-width: 750px;">
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
            print(current_month, current_year)
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
        content['title'] = 'Отчет'
        content['current_year'] = current_year
        content['current_month'] = current_month

        return content
