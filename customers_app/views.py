import datetime
import hashlib
import json
import uuid
from collections import defaultdict
from io import BytesIO
from itertools import chain
# from pprint import pprint
# from pydoc import pager
from urllib.parse import urlencode

import pandas as pd
import qrcode
# from celery.worker.consumer import Tasks
# from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, DAILY
from decouple import config
# from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
# from django.db.models.signals import post_save
from django.template.loader import render_to_string
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from loguru import logger
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q, F
from django.http import JsonResponse, QueryDict, HttpResponse
from django.shortcuts import render, HttpResponseRedirect, redirect, get_object_or_404
from django.views.generic import DetailView, UpdateView, CreateView, ListView

from administration_app.models import PortalProperty
from administration_app.utils import boolean_return, get_jsons_data, \
    change_session_get, change_session_context, format_name_initials, get_year_interval, get_client_ip, adjust_time, \
    process_group, process_group_interval, seconds_to_hhmm, get_active_user, get_today_data_delta
from contracts_app.models import TypeDocuments, Contract
from contracts_app.templatetags.custom import FIO_format
from customers_app.customers_util import get_database_user_work_profile, get_database_user, get_identity_documents, \
    get_settlement_sheet, get_report_card_table, get_vacation_days
from customers_app.models import DataBaseUser, Posts, Counteragent, Division, Job, AccessLevel, \
    DataBaseUserWorkProfile, Citizenships, IdentityDocuments, HarmfulWorkingConditions, Groups, CounteragentDocuments, \
    UserStats
from customers_app.models import DataBaseUserProfile as UserProfile
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, PostsAddForm, \
    CounteragentUpdateForm, StaffUpdateForm, DivisionsAddForm, DivisionsUpdateForm, JobsAddForm, JobsUpdateForm, \
    CounteragentAddForm, PostsUpdateForm, GroupAddForm, GroupUpdateForm, ChangePassPraseUpdateForm, \
    ChangeAvatarUpdateForm, CounteragentDocumentsAddForm, CounteragentDocumentsUpdateForm
from django.contrib import auth
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

# from hrdepartment_app.hrdepartment_util import get_working_hours
from hrdepartment_app.models import OfficialMemo, ApprovalOficialMemoProcess, ReportCard, ProductionCalendar, \
    get_norm_time_at_custom_day
from hrdepartment_app.tasks import send_email_single_notification
from tasks_app.models import Task

logger.add("debug_users.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'))


@login_required
def lock_screen(request):
    if request.method == 'POST':
        password = request.POST.get('pwd')
        user = auth.authenticate(username=request.user.username, password=password)
        # user = authenticate(request, username=request.user.username, password=password)
        if user is not None:
            auth.login(request, user)
            request.session['locked'] = False  # Снимаем блокировку
            return redirect('customers_app:profile', pk=request.user.pk)  # Перенаправляем на страницу профиля
        else:
            return render(request, 'customers_app/lock_screen.html', {'error': 'Неверный пароль'})
    request.session['locked'] = True  # Устанавливаем блокировку
    return render(request, 'customers_app/lock_screen.html')


@login_required
def generate_qr_code(request, current_url):
    # Генерируем уникальный токен для авторизации
    token = get_random_string(length=32)

    # Сохраняем токен в кеше с привязкой к пользователю
    cache.set(token, request.user.id, timeout=30)  # Токен действителен 5 минут

    # Создаем параметры для URL
    params = {
        'token': token,
        'next': current_url,
    }

    # Получаем полный URL для авторизации с токеном и текущим URL
    auth_url_string = reverse('customers_app:auth_with_token')
    auth_url = request.build_absolute_uri(auth_url_string) + '?' + urlencode(params)

    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(auth_url)
    qr.make(fit=True)

    # Создаем изображение QR-кода
    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем изображение в буфер
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    # Возвращаем изображение в ответе
    return HttpResponse(buffer.getvalue(), content_type="image/png")


def auth_with_token(request):
    token = request.GET.get('token')
    next_url = request.GET.get('next')
    if token:
        user_id = cache.get(token)
        if user_id:
            try:
                user = DataBaseUser.objects.get(id=user_id)
                auth.login(request, user)
                cache.delete(token)  # Удаляем токен после использования
                return redirect(next_url)  # Перенаправляем на указанный URL
            except DataBaseUser.DoesNotExist:
                pass
    return redirect('customers_app:login')  # Перенаправляем на страницу входа, если токен недействителен


class GroupListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Groups
    template_name = 'customers_app/group_list.html'
    success_url = reverse_lazy('customers_app:group_list')
    permission_required = 'customers_app.view_groups'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            group_list = Groups.objects.all()
            data = [group_item.get_data() for group_item in group_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Группы'
        return context


class GroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Groups
    form_class = GroupAddForm
    template_name = 'customers_app/group_form.html'
    success_url = reverse_lazy('customers_app:group_list')
    permission_required = 'customers_app.add_groups'


class GroupUpdateView(LoginRequiredMixin, UpdateView):
    model = Groups
    form_class = GroupUpdateForm
    template_name = 'customers_app/group_form.html'
    success_url = reverse_lazy('customers_app:group_list')


def get_model_fields(model_object):
    return model_object._meta.fields


@logger.catch
def get_profile_fill(self, context):
    profile_info = 0
    user_object = self.get_object()
    user_private = user_object.user_profile
    user_work = user_object.user_work_profile
    user_object_list = ['first_name', 'last_name', 'email', 'surname', 'avatar', 'birthday', 'address',
                        'personal_phone', 'gender']
    user_private_list = ['citizenship', 'passport', 'snils', 'oms', 'inn']
    user_work_list = ['date_of_employment', 'internal_phone', 'job', 'divisions']
    for item in get_model_fields(user_object):
        if str(item).split('.')[2] in user_object_list:
            if getattr(user_object, str(item).split('.')[2]):
                profile_info += 5.555555556
    try:
        for item in get_model_fields(user_private):
            if str(item).split('.')[2] in user_private_list:
                if getattr(user_private, str(item).split('.')[2]):
                    profile_info += 5.555555556
                    context['user_private'] = True
    except Exception as _ex:
        logger.info(f'{_ex}: Отсутствует блок личной информации')
    try:
        for item in get_model_fields(user_work):
            if str(item).split('.')[2] in user_work_list:
                if getattr(user_work, str(item).split('.')[2]):
                    profile_info += 5.555555556
                    context['user_work'] = True
    except Exception as _ex:
        logger.info(f'{_ex}: Отсутствует блок рабочей информации')
    context['profile_info'] = f"{profile_info:.0f}"


@login_required
def index(request):
    document_types = TypeDocuments.objects.all()
    category = list()
    for item in document_types:
        category.append(item.type_document)
    values = list()
    for item in document_types:
        values.append(Contract.objects.filter(type_of_document=item).count())
    types_count = dict(zip(category, values))
    return render(request, 'customers_app/customers.html', context={'types_count': types_count})


class DataBaseUserProfileDetail(LoginRequiredMixin, DetailView):
    context = {}
    model = DataBaseUser
    template_name = 'customers_app/user_profile.html'

    # @method_decorator(user_passes_test(lambda u: u.is_active))
    # def dispatch(self, request, *args, **kwargs):
    #     user_object = self.get_object()
    #     if request.user.pk == user_object.pk or request.user.is_superuser:
    #         return super(DataBaseUserProfileDetail, self).dispatch(request, *args, **kwargs)
    #     else:
    #         raise PermissionDenied

    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        if not self.request.user.is_superuser:
            qs = qs.filter(pk=self.request.user.pk)
        return qs

    def get_task_title_with_icon(self, task):
        """
        Возвращает название задачи с иконкой в зависимости от приоритета.
        """
        if isinstance(task, Task):
            if task.user != self.request.user:
                return f'<i class="fas fa-user-friends"></i> {task.title}'
            if task.priority == 'primary':
                return f'<i class="fas fa-star"></i> {task.title}'  # Звезда для основного приоритета
            elif task.priority == 'warning':
                return f'<i class="fas fa-exclamation-triangle"></i> {task.title}'  # Предупреждение для предупреждающего приоритета
            elif task.priority == 'info':
                return f'<i class="fas fa-info-circle"></i> {task.title}'  # Информация для информационного приоритета
            elif task.priority == 'danger':
                return f'<i class="fas fa-exclamation-circle"></i> {task.title}'  # Ошибка для опасного приоритета
            elif task.priority == 'dark':
                return f'<i class="fas fa-moon"></i> {task.title}'  # Луна для темного приоритета
            else:
                return task.title
        if isinstance(task, Posts):
            if "День рождения" in task.post_title:
                return f'<i class="fas fa-birthday-cake"></i> {task.post_title}'
            else:
                return task.post_title

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserProfileDetail, self).get_context_data(**kwargs)
        user_obj = self.get_object()  # DataBaseUser.objects.get(pk=self.request.user.pk)
        # print(context['databaseuser'].pk)
        post_obj = Posts.objects.all().exclude(post_date_end__lt=datetime.datetime.today())

        try:
            # Получаем выборку постов, у которых дата начала больше текущего дня
            post_high = post_obj.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                        Q(post_date_start__gt=datetime.datetime.today())).order_by(
                '-post_date_start')
            # Получаем выборку постов, у которых дата начала меньше текущего дня
            post_low = post_obj.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                       Q(post_date_start__lte=datetime.datetime.today())).order_by(
                '-post_date_start')
            context['post_high'] = post_high
            context['post_low'] = post_low
        except Exception as _ex:
            message = f'{user_obj}, У пользователя отсутствует подразделение!!!: {_ex}'
            logger.debug(message)
        month_dict, year_dict = get_year_interval(2020)
        context['year_dict'] = year_dict
        context['month_dict'] = month_dict
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Профиль ' + str(
            format_name_initials(user_obj))
        context['sp'] = OfficialMemo.objects.filter(cancellation=False).count()
        context['spf'] = OfficialMemo.objects.filter(cancellation=True).count()
        context['bp'] = ApprovalOficialMemoProcess.objects.filter(cancellation=False).count()
        context['bpf'] = ApprovalOficialMemoProcess.objects.filter(cancellation=True).count()
        context['contract'] = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True),
                                                      Q(type_of_document__type_document='Договор')).count()
        context['current_year'] = datetime.datetime.today().year
        context['current_month'] = str(datetime.datetime.today().month)
        get_profile_fill(self, context)

        posts_list = Posts.objects.all()
        tasks_list = Task.objects.all()
        repeat_tasks = []
        # for task in posts_list:
        #     post_date_start = datetime.datetime.combine(task.post_date_start, datetime.datetime.min.time(), tzinfo=datetime.timezone.utc)
        #     post_date_end = datetime.datetime.combine(task.post_date_end, datetime.datetime.min.time(), tzinfo=datetime.timezone.utc)
        #     repeat_tasks.append({
        #         'title': task.post_title,  # Получаем название задачи с иконкой task.title,
        #         'rrule': {
        #             'freq': 'daily',  # Используем поле repeat для freq
        #             'dtstart': post_date_start.isoformat(), # Начальная дата с временной зоной
        #             'until': post_date_end.isoformat(), # Конечная дата с временной зоной
        #         },
        #         'url': reverse('customers_app:post', args=[task.pk]),
        #         'color': 'info',
        #     })
        # Объединяем оба списка в один итерируемый объект
        combined_list = chain(posts_list, tasks_list)

        for item in combined_list:
            if isinstance(item, Posts):  # Проверяем, является ли элемент объектом Posts
                # Обработка для posts_list
                post_date_start = datetime.datetime.combine(item.post_date_start, datetime.datetime.min.time(),
                                                            tzinfo=datetime.timezone.utc)
                post_date_end = datetime.datetime.combine(item.post_date_end, datetime.datetime.min.time(),
                                                          tzinfo=datetime.timezone.utc)

                repeat_tasks.append({
                    'title': self.get_task_title_with_icon(item),  # Получаем название задачи
                    'rrule': {
                        'freq': 'daily',  # Используем поле repeat для freq
                        'dtstart': post_date_start.isoformat(),  # Начальная дата с временной зоной
                        'until': post_date_end.isoformat(),  # Конечная дата с временной зоной
                    },
                    'url': reverse('customers_app:post', args=[item.pk]),
                    'color': 'info',
                })
            elif isinstance(item, Task):  # Проверяем, является ли элемент объектом Task
                # Обработка для tasks_list
                if (self.request.user == item.user) or (self.request.user in item.shared_with.iterator()):
                    repeat_tasks.append({
                        'title': self.get_task_title_with_icon(item),  # Получаем название задачи
                        'rrule': {
                            'freq': 'daily',  # Используем поле repeat для freq
                            'dtstart': item.start_date.isoformat(),  # Начальная дата с временной зоной
                            'until': item.start_date.isoformat(),  # Конечная дата с временной зоной
                        },
                        'url': reverse('tasks_app:task-update', args=[item.pk]),
                        'color': item.priority,
                    })
        context['repeat_tasks'] = repeat_tasks

        # print(repeat_tasks)
        # context.update(groups())
        return context

    def get(self, request, *args, **kwargs):

        if self.request.GET:
            current_year = self.request.GET.get('CY')
            current_month = self.request.GET.get('CM')
            report_year = self.request.GET.get('RY')
            report_month = self.request.GET.get('RM')
            current_passphrase = self.request.GET.get('PX')
            get_date = self.request.GET.get('GD')
            if current_month and current_year:
                try:
                    if len(current_month) == 1:
                        current_month = '0' + current_month
                    get_user_obj = self.get_object()
                except TypeError:
                    logger.error(f'Ошибка передачи запроса, curent_month не содержит значение!')
                    # ToDo: Пришел запрос с поисковой строки
                    # print(self.request.GET.get('q'))
                    return super().get(request, *args, **kwargs)
                hash_pass = hashlib.sha256(current_passphrase.encode()).hexdigest()
                hash_null = hashlib.sha256(''.encode()).hexdigest()
                if hash_pass == request.user.passphrase and hash_pass != hash_null:
                    html_obj = get_settlement_sheet(current_month, current_year, get_user_obj.person_ref_key)
                else:
                    html_obj = ['', '', '']
                return JsonResponse(html_obj, safe=False)
            if report_year and report_month:
                """
                # Получение отработанных дней
                # data_dict, total_score, first_day, last_day, user_start_time, user_end_time = get_report_card(self.request.user.pk, RY=report_year, RM=report_month)
                data_dict, total_score, first_day, last_day, user_start, user_end = get_working_hours(
                    self.request.user.pk, datetime.datetime(year=int(report_year), month=int(report_month), day=1))

                # print(data_dict, total_score, first_day, last_day, user_start_time, user_end_time)
                return JsonResponse(
                    get_report_card_table(data_dict, total_score, first_day, last_day, user_start, user_end),
                    safe=False)
                """
                # Определяем текущую дату
                current_date = datetime.datetime.today()  # - datetime.timedelta(days=1)

                # Определяем начальную дату как первый день текущего месяца
                start_date = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                # Генерируем диапазон дат с начала месяца до текущего дня
                norm_time_date = ProductionCalendar.objects.get(
                    calendar_month=datetime.datetime(int(report_year), int(report_month), 1))

                if int(report_month) == current_date.month and int(report_year) == current_date.year:
                    # Если текущий месяц и текущая дата совпадают, то диапазон дат с начала месяца до текущего дня.
                    dates = list(rrule(DAILY, dtstart=start_date, until=current_date))
                    norm_time = norm_time_date.get_norm_time_on_day()
                else:
                    # Создаем конечную дату (последний день месяца)
                    # Мы вычисляем его, переходя на следующий месяц и вычитая один день.
                    norm_time = norm_time_date.get_norm_time()
                    # print(report_month)
                    if int(report_month) == 12:
                        end_date = datetime.datetime(int(report_year), 12, 31)
                    else:
                        end_date = datetime.datetime(int(report_year), int(report_month) + 1, 1) - datetime.timedelta(
                            days=1)
                    dates = list(rrule(DAILY,
                                       dtstart=datetime.datetime(year=int(report_year), month=int(report_month), day=1,
                                                                 hour=0, minute=0, second=0), until=end_date))
                report_card_list = []

                for report_record in ReportCard.objects.filter(
                        Q(employee=self.request.user) & Q(report_card_day__in=dates)):
                    report_card_list.append(
                        [report_record.report_card_day, report_record.start_time,
                         report_record.end_time, report_record.record_type])
                # field names
                fields = ["Дата", "Start", "End", "Type"]

                # Создание DataFrame
                df = pd.DataFrame(report_card_list, columns=fields)
                # Преобразование столбцов в нужные типы данных
                df["Дата"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y")
                df["Start"] = pd.to_datetime(df["Start"], format="%H:%M:%S")
                df["End"] = pd.to_datetime(df["End"], format="%H:%M:%S")
                df["Type"] = df["Type"].astype(int)

                # Группируем по FIO и Date и применяем функцию
                df = df.groupby(["Дата"]).apply(adjust_time).reset_index(drop=True)

                # Вычисление разности между End и Start и сохранение в новом столбце Time

                df["Time"] = (df["End"] - df["Start"]).apply(
                    lambda x: x.total_seconds() if x.total_seconds() > 0 else 0)  # В часах
                # Группируем по дате и применяем функцию

                df = df.groupby('Дата').apply(process_group_interval).reset_index(drop=True)
                # Группируем по FIO и Date и применяем функцию

                # df = df.groupby(["Дата", "Интервал"]).apply(process_group).reset_index(name="Time")
                df = df.groupby(["Дата", "Интервал"]).apply(process_group).reset_index(drop=True)

                # Вычисление разности между End и Start и сохранение в новом столбце Time
                type_of_report = {
                    1: "Явка",
                    2: "Отпуск",
                    3: "Дополнительный ежегодный отпуск",
                    4: "Отпуск за свой счет",
                    5: "Дополнительный учебный отпуск",
                    6: "Отпуск по уходу за ребенком",
                    7: "Дополнительный неоплачиваемый отпуск",
                    8: "Отпуск по беременности и родам",
                    9: "Отпуск без оплаты согласно ТК РФ",
                    10: "Дополнительный отпуск",
                    11: "Дополнительный оплачиваемый отпуск",
                    12: "Основной",
                    13: "Ручной ввод",
                    14: "Служебная поездка",
                    15: "Командировка",
                    16: "Больничный",
                    17: "Мед осмотр",
                    18: "График отпусков",
                    19: "Отпуск на санаторно курортное лечение",
                    20: "Отгул",
                }
                df['Тип'] = df['Type'].map(type_of_report)

                # Генерация полного диапазона дат за месяц
                full_date_range = pd.date_range(start=dates[0], end=dates[-1], freq='D')

                # Создание DataFrame с полным диапазоном дат
                full_df = pd.DataFrame({'Дата': full_date_range})

                # Объединение существующих данных с полным диапазоном дат
                df = pd.merge(full_df, df, on='Дата', how='outer')
                # Заполнение недостающих данных

                df['Интервал'] = df['Интервал'].fillna('0:00-0:00')
                df['Time'] = df['Time'].fillna(0)
                df['Type'] = df['Type'].fillna(100).astype(int)

                # Фильтрация DataFrame по условию Тип = NaN
                filtered_df = df[df['Тип'].isna()]

                # Применение функции get_norm_time_at_custom_day к каждой строке
                filtered_df['Тип'] = filtered_df['Дата'].apply(
                    lambda day: get_norm_time_at_custom_day(day, True))

                # Обновление поля Тип в исходном DataFrame
                df.update(filtered_df)

                # Проверяем корректность заполнения столбца 'Time', если 14, 15, 16, 17, 20, то устанавливаем время согласно производственному календарю.
                df['Time'] = df.apply(
                    lambda row: row['Time'] if row['Type'] not in [14, 15, 16, 17, 20] else get_norm_time_at_custom_day(
                        row['Дата'], type_of_day=row['Type']), axis=1)
                # Вычисление разности между временем введенным и временем по производственному календарю
                df['+/-'] = df.apply(lambda row: row['Time'] - get_norm_time_at_custom_day(row['Дата']), axis=1)
                # Получение общей суммы времени за все дни
                total_time = df['Time'].sum()
                # Применяем функцию seconds_to_hhmm к колонке '+/-' для приведения к нужному формату: hh:mm
                df['+/-'] = df['+/-'].apply(seconds_to_hhmm)
                delta = (total_time - norm_time * 3600)
                total_time_hhmm = seconds_to_hhmm(delta)

                # Блок для ввода в таблицу строки за текущий день. Если дата равна текущей, то добавляем в dataframe строку с текущей датой
                if int(report_month) == current_date.month and int(report_year) == current_date.year:
                    report_card_day = ReportCard.objects.filter(
                        Q(employee=self.request.user) & Q(report_card_day=datetime.datetime.today())).values_list(
                        'report_card_day', 'start_time',
                        'end_time', 'record_type')
                    if len(report_card_day) > 0:
                        end_time = 'по н.в.'
                        current_df = pd.DataFrame(report_card_day, columns=fields)
                        current_df["Дата"] = pd.to_datetime(current_df["Дата"], format="%d.%m.%Y")
                        current_df["Start"] = pd.to_datetime(current_df["Start"], format="%H:%M:%S")
                        current_df["End"] = pd.to_datetime(current_df["End"], format="%H:%M:%S")
                        current_df["Type"] = current_df["Type"].astype(int)
                        current_df["Time"] = (current_df["End"] - current_df["Start"]).dt.total_seconds()
                        # Группируем по дате и применяем функцию
                        current_df = current_df.groupby('Дата').apply(process_group_interval).reset_index(drop=True)
                        current_df = current_df.groupby(["Дата", "Интервал"]).apply(process_group).reset_index(
                            drop=True)
                        start_interval = (current_df["Интервал"][0].split('-'))[0]
                        total_row = pd.DataFrame({
                            'Дата': [current_df["Дата"][0].strftime('%d.%m.%Y')],
                            'Интервал': [f"{start_interval} - {end_time}"],
                            '+/-': ['--//--']
                        })
                        total_row["Дата"] = pd.to_datetime(total_row["Дата"], format="%d.%m.%Y")
                        # df = pd.concat([df, total_row], ignore_index=True)
                    else:
                        total_row = pd.DataFrame({
                            'Дата': [datetime.datetime.today()],
                            'Интервал': ["Нет отметки"],
                            '+/-': ['--//--']
                        })
                        total_row["Дата"] = pd.to_datetime(total_row["Дата"], format="%d.%m.%Y")
                        # df = pd.concat([df, total_row], ignore_index=True)

                # Добавляем новую строку с суммой в конец DataFrame
                total_row = pd.DataFrame({
                    'Дата': ['Итого'],
                    'Интервал': [''],
                    '+/-': [total_time_hhmm]
                })
                df["Дата"] = df["Дата"].dt.strftime("%d")
                df = pd.concat([df, total_row], ignore_index=True)
                df['Тип'] = df['Тип'].fillna(' ')
                # Выводим строковое представление интервала
                # df = df.sort_values(by=['Дата'])
                # print(df.head(31), '\n')
                df.style.background_gradient(cmap='viridis')
                html = df[["Дата", "Интервал", "+/-", "Тип"]].to_html(
                    classes='table table-light table-striped-columns table-hover table-bordered mb-0',
                    table_id='my_table_id',
                    index=False,
                    header=True,
                    formatters={'Time': '{:.2f}'.format, },
                    border=1,
                    # attrs={'style': 'border-collapse: collapse;'},
                    # caption='Моя таблица',
                    justify='right',
                )
                return JsonResponse(html, safe=False)

            if get_date:
                # Получение остатка отпусков
                html = f"<label class='form-control form-control-modern'>Остаток отпуска: {get_vacation_days(self, get_date)} дн.</label>"

                return JsonResponse(html, safe=False)
        return super().get(request, *args, **kwargs)


class ChangePassPraseUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    form_class = ChangePassPraseUpdateForm
    template_name = 'customers_app/change_passphrase.html'


class ChangeAvatarUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    form_class = ChangeAvatarUpdateForm
    template_name = 'customers_app/change_avatar.html'


# def change_password(request):
#
#     if request.method == 'POST':
#         form = ChangePasswordForm(request.POST)
#         if form.is_valid():
#             user = request.user
#             user.set_password(form.cleaned_data['new_password'])
#             user.save()
#             update_session_auth_hash(request, user)
#             return redirect('customers_app:profile')
#     else:
#         form = ChangePasswordForm()
#     return render(request, 'customers_app/change_password.html', {'form': form})

# class DataBaseUserUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
#     model = DataBaseUser
#     template_name = 'customers_app/user_profile_update.html'
#     form_class = DataBaseUserUpdateForm
#     permission_required = 'customers_app.change_databaseuser'
#
#     def get_context_data(self, **kwargs):
#         context = super(DataBaseUserUpdate, self).get_context_data(**kwargs)
#         user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
#         try:
#             post = Posts.objects.filter(post_divisions__pk=user_obj.user_work_profile.divisions.pk).order_by(
#                 'creation_date').reverse()
#             context['posts'] = post
#         except Exception as _ex:
#             message = f'{user_obj}, Ошибка получения записей. У пользователя |{user_obj.username}| отсутствует подразделение!!!: {_ex}'
#             logger.error(message)
#
#         context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Профиль пользователя'
#
#         context['sp'] = OfficialMemo.objects.all().count()
#         context['bp'] = ApprovalOficialMemoProcess.objects.all().count()
#         context['contract'] = Contract.objects.all().count()
#         get_profile_fill(self, context)
#         return context
#
#     def get_success_url(self):
#         pk = self.request.user.pk
#         return reverse("customers_app:profile", kwargs={"pk": pk})
#
#     def get(self, request, *args, **kwargs):
#         """
#         Проверка пользователя, при попытке отредактировать профиль другого пользователя путем подстановки в адресной
#         строке чужого ID, будет произведено перенаправление пользователя на свою страницу с профилем.
#         :param request: Передаваемый запрос
#         :param kwargs: Получаем передаваемый ID пользователя из строки в браузере
#         :return: В случае подмены ID выполняет редирект 302
#         """
#         if self.request.user.pk != self.kwargs['pk']:
#             url_match = reverse('customers_app:profile', kwargs={"pk": self.request.user.pk})
#             return redirect(url_match)
#         return super(DataBaseUserUpdate, self).get(request, *args, **kwargs)


# def login(request):
#     content = {'title': 'вход'}
#     login_form = DataBaseUserLoginForm(data=request.POST)
#     content['login_form'] = login_form
#     logger.info(get_client_ip(request))
#     if request.method == 'POST' and login_form.is_valid():
#         username = request.POST['username']
#         password = request.POST['password']
#         user = auth.authenticate(username=username, password=password)
#         portal = PortalProperty.objects.all()
#         if user and user.is_active:
#             auth.login(request, user)
#             logger.info(f'Успешный вход. {user}')
#             try:
#                 portal_session = portal.first().portal_session
#             except Exception as _ex:
#                 portal_session = 3600
#                 logger.info(f'{_ex}: Не заданы базовые параметры длительности сессии пользователя')
#             try:
#                 portal_paginator = portal.first().portal_paginator
#             except Exception as _ex:
#                 portal_paginator = 10
#                 logger.info(f'{_ex}: Не заданы базовые параметры пагинации страниц')
#             request.session.set_expiry(portal_session)
#             request.session['portal_paginator'] = portal_paginator
#             request.session['current_month'] = int(datetime.datetime.today().month)
#             request.session['current_year'] = int(datetime.datetime.today().year)
#             # return HttpResponseRedirect(reverse('customers_app:index'))  # , args=(user,))
#             return HttpResponseRedirect(reverse_lazy('customers_app:profile', args=(user.pk,)))  # , args=(user,))
#     else:
#         try:
#             logger.error(f'Ошибка авторизации!!! {request.POST["username"]}, IP: {get_client_ip(request)}')
#         except Exception as _ex:
#             logger.error(f'Ошибка!!! {_ex}')
#     # else:
#     #     content['errors'] = login_form.get_invalid_login_error()
#     return render(request, 'customers_app/login.html', content)


def login(request):
    content = {'title': 'Вход в систему'}
    if request.method == 'POST':
        login_form = DataBaseUserLoginForm(data=request.POST)
        content['login_form'] = login_form
        logger.info(get_client_ip(request))
        if login_form.is_valid():
            username = login_form.cleaned_data['username']
            password = login_form.cleaned_data['password']
            user = auth.authenticate(username=username, password=password)
            portal = PortalProperty.objects.all()
            if user and user.is_active:
                auth.login(request, user)
                logger.info(f'Успешный вход. {user}')
                try:
                    portal_session = portal.first().portal_session
                except Exception as _ex:
                    portal_session = 3600
                    logger.info(f'{_ex}: Не заданы базовые параметры длительности сессии пользователя')
                try:
                    portal_paginator = portal.first().portal_paginator
                except Exception as _ex:
                    portal_paginator = 10
                    logger.info(f'{_ex}: Не заданы базовые параметры пагинации страниц')
                request.session.set_expiry(portal_session)
                request.session['portal_paginator'] = portal_paginator
                request.session['current_month'] = int(datetime.datetime.today().month)
                request.session['current_year'] = int(datetime.datetime.today().year)
                return HttpResponseRedirect(reverse_lazy('customers_app:profile', args=(user.pk,)))
            else:
                content['errors'] = 'Неверный логин или пароль.'
                logger.error(f'Ошибка авторизации: Неверные учетные данные для пользователя {username}, IP: {get_client_ip(request)}')
        else:
            content['errors'] = login_form.errors # Или login_form.non_field_errors()
            try:
                logger.error(f'Ошибка валидации формы при входе. Данные: {request.POST}, IP: {get_client_ip(request)}')
            except Exception as _ex:
                logger.error(f'Ошибка при логировании ошибки валидации: {_ex}')
    else:
        content['login_form'] = DataBaseUserLoginForm()
    return render(request, 'customers_app/login.html', content)

def logout(request):
    auth.logout(request)
    return HttpResponseRedirect(reverse('customers_app:login'))


class SignUpView(CreateView):
    template_name = 'customers_app/register.html'
    form_class = DataBaseUserRegisterForm
    model = DataBaseUser
    success_url = reverse_lazy('customers_app:login')

    def form_valid(self, form):
        valid = super().form_valid(form)
        login(self.request)
        return valid


def validate_username(request):
    """Проверка доступности логина"""
    username = request.GET.get('username', None)
    response = {
        'is_taken': DataBaseUser.objects.filter(username__iexact=username).exists()
    }
    return JsonResponse(response)


class PostsAddView(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'customers_app/posts_add.html'
    form_class = PostsAddForm
    model = Posts
    permission_required = 'customers_app_posts.add_posts'

    def get_context_data(self, **kwargs):
        context = super(PostsAddView, self).get_context_data()
        context['users'] = DataBaseUser.objects.get(pk=self.request.user.pk)
        return context

    def get_success_url(self):
        """
        Получение URL при удачном добавлении нового сообщения. Получаем ID пользователя из request, и передача его
        в качестве параметра
        :return: Возвращает URL адрес страницы, с которой создавалось сообщение.
        """
        pk = self.request.user.pk
        return reverse("customers_app:profile", kwargs={"pk": pk})


class PostsListView(LoginRequiredMixin, ListView):
    template_name = 'customers_app/posts_list.html'
    model = Posts
    paginate_by = 6

    def get_queryset(self):
        user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
        qs = Posts.objects.filter(post_divisions__pk=user_obj.user_work_profile.divisions.pk).order_by('pk').reverse()
        return qs


class PostsDetailView(LoginRequiredMixin, DetailView):
    template_name = 'customers_app/posts_detail.html'
    model = Posts

    def get_success_url(self):
        return reverse('customers_app:profile', kwargs={'pk': self.request.user.pk})


class PostsUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'customers_app/posts_detail_update.html'
    model = Posts
    form_class = PostsUpdateForm

    def get_success_url(self):
        """
               Получение URL при удачном добавлении нового сообщения. Получаем ID пользователя из request, и передача
               его в качестве параметра
               :return: Возвращает URL адрес страницы, с которой создавалось сообщение.
               """
        # pk = self.request.user.pk
        return reverse("customers_app:post_list")


class CounteragentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    # template_name = 'customers_app/counteragent_list.html'  # Совпадает с именем по умолчании
    model = Counteragent
    paginate_by = 6
    permission_required = 'customers_app.view_counteragent'

    def get_queryset(self):
        qs = Counteragent.objects.all().order_by('pk')
        return qs

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            counteragent_list = Counteragent.objects.all()
            data = [counteragent_item.get_data() for counteragent_item in counteragent_list]
            response = {'data': data}
            return JsonResponse(response)
        count = 0
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "Контрагенты", 1)
            # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
            for item in todos['value']:
                if not item['IsFolder']:
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'short_name': item['Description'],
                        'full_name': item['НаименованиеПолное'],
                        'inn': item['ИНН'],
                        'kpp': item['КПП'],
                        'ogrn': item['РегистрационныйНомер'],
                        'base_counteragent': False,
                    }
                    Counteragent.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**divisions_kwargs})
                    count += 1
            url_match = reverse_lazy('customers_app:counteragent_list')
            return redirect(url_match)
        change_session_get(self.request, self)
        return super(CounteragentListView, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(CounteragentListView, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Список контрагентов'
        change_session_context(context, self)
        return context


class CounteragentAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Counteragent
    form_class = CounteragentAddForm
    template_name = 'customers_app/counteragent_add.html'
    permission_required = 'customers_app.add_counteragent'

    def get_context_data(self, **kwargs):
        context = super(CounteragentAdd, self).get_context_data(**kwargs)
        # context['counteragent_users'] = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
        # context['type_counteragent'] = Counteragent.type_of
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)
        # if content['director'] == 'none':
        #     content.setlist('director', '')
        # if content['accountant'] == 'none':
        #     content.setlist('accountant', '')
        # if content['contact_person'] == 'none':
        #     content.setlist('contact_person', '')
        self.request.POST = content
        return super(CounteragentAdd, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            refreshed_form = form.save(commit=False)
            refreshed_form.ref_key = uuid.uuid4()
            refreshed_form.save()
        return HttpResponseRedirect(reverse('customers_app:counteragent_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class CounteragentDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    # template_name = 'customers_app/counteragent_detail.html'  # Совпадает с именем по умолчании
    model = Counteragent
    permission_required = 'customers_app.view_counteragent'


class CounteragentUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    # template_name = 'customers_app/counteragent_form.html'  # Совпадает с именем по умолчании
    model = Counteragent
    form_class = CounteragentUpdateForm
    permission_required = 'customers_app.change_counteragent'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(reverse('customers_app:login'))
        return super(CounteragentUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(CounteragentUpdate, self).get_context_data(**kwargs)
        context['counteragent_docs'] = CounteragentDocuments.objects.filter(package=self.object)
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)
        # if content['director'] == 'none':
        #     content.setlist('director', '')
        # if content['accountant'] == 'none':
        #     content.setlist('accountant', '')
        # if content['contact_person'] == 'none':
        #     content.setlist('contact_person', '')
        self.request.POST = content
        return super(CounteragentUpdate, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            refreshed_form = form.save(commit=False)
            if refreshed_form.ref_key == "":
                refreshed_form.ref_key = uuid.uuid4()
            refreshed_form.save()
        return HttpResponseRedirect(reverse('customers_app:counteragent', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class StaffListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = 'customers_app/staff_list.html'
    model = DataBaseUser
    sorted_list = ['pk', 'last_name', 'user_work_profile__divisions__code', 'user_work_profile__job__name']
    permission_required = 'customers_app.view_databaseuser'

    def get_context_data(self, **kwargs):
        context = super(StaffListView, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Список пользователей'
        return context

    def get_queryset(self):
        qs = DataBaseUser.objects.all().order_by('pk').exclude(username='proxmox').exclude(is_active=False).exclude(
            is_ppa=True)
        return qs

    def get(self, request, *args, **kwargs):

        if self.request.GET.get('update') == '3':
            users_set = DataBaseUser.objects.all().exclude(is_ppa=True)
            for user in users_set:
                if not get_active_user(user.ref_key):
                    user.is_active = False
                    user.save()

        if self.request.GET.get('update') == '2':
            get_identity_documents()

        if self.request.GET.get('update') == '1':
            get_database_user_work_profile()

        if self.request.GET.get('update') == '0':
            # Загрузка сотрудников из базы 1С
            get_database_user()
            url_match = reverse_lazy('customers_app:staff_list')
            return redirect(url_match)

        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            baseusers = DataBaseUser.objects.all().order_by('last_name').exclude(username='proxmox').exclude(
                is_active=False).exclude(is_ppa=True)
            data = [baseuser.get_data() for baseuser in baseusers]
            response = {'data': data}
            return JsonResponse(response)

        return super(StaffListView, self).get(request, *args, **kwargs)


class StaffDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    template_name = 'customers_app/staff_detail.html'  # Совпадает с именем по умолчании
    model = DataBaseUser
    permission_required = 'customers_app.view_databaseuser'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(reverse('customers_app:login'))
        user_object = self.get_object()
        if request.user.pk == user_object.pk or request.user.is_superuser or request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        else:
            logger.warning(f'Пользователь {request.user} хотел получить доступ к пользователю {user_object.username}')
            raise PermissionDenied

    # def get(self, request, *args, **kwargs):
    #     if self.request.GET.get('update') == '0':
    #         user_object = self.get_object()
    #         if user_object.user_work_profile.work_email_password:
    #             user_object.set_password(user_object.user_work_profile.work_email_password)
    #             user_object.save()
    #             print(f'changed to <<{user_object.user_work_profile.work_email_password}>> successfully')
    #         else:
    #             context = {
    #                 'error': 'Не смог изменить пароль'
    #             }
    #             self.get_context_data(context)
    #     return super(StaffDetail, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_object = self.get_object()
        context['birthday_difference'] = get_today_data_delta(user_object.birthday, 1)
        context['employment_difference'] = get_today_data_delta(user_object.user_work_profile.date_of_employment, 0)
        # Получаем параметр запроса 'value'
        value = self.request.GET.get('update')

        if value == '0':
            try:

                if user_object.user_work_profile.work_email_password != '':
                    user_object.set_password(user_object.user_work_profile.work_email_password)
                    user_object.save()
                    pk = user_object.pk
                    send_email_single_notification.delay(pk)
                    context[
                        'pass_change'] = f'Для сотрудника: {FIO_format(user_object.title)} изменен пароль для входа на корпоративный сайт, на: {user_object.user_work_profile.work_email_password}, успешно. Письмо с учетными данными отправлено сотруднику на почту.'
                else:
                    context['pass_change'] = 'Отсутствует пароль!'

            except ValueError:
                context['pass_change'] = "Invalid value"

        return context


class StaffUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = 'customers_app/staff_form.html'
    model = DataBaseUser
    form_class = StaffUpdateForm
    permission_required = 'customers_app.change_databaseuser'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(reverse('customers_app:login'))
        return super().dispatch(request, *args, **kwargs)
        # user_object = self.get_object()
        # if request.user.pk == user_object.pk or request.user.is_superuser:
        #     return super().dispatch(request, *args, **kwargs)
        # else:
        #     logger.warning(f'Пользователь {request.user} хотел получить доступ к пользователю {user_object.username}')
        #     raise PermissionDenied

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:staff', args=[self.object.pk]))

    def get_context_data(self, **kwargs):
        context = super(StaffUpdate, self).get_context_data(**kwargs)
        context['all_gender'] = DataBaseUser.type_of_gender
        context['all_type_user'] = DataBaseUser.type_of
        context['all_division'] = Division.objects.all()
        context['all_job'] = Job.objects.all()
        context['all_access'] = AccessLevel.objects.all().reverse()
        context['all_citizenship'] = Citizenships.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)

        if content['type_users'] == 'none':
            content.setlist('type_users', '')
        if content['gender'] == 'none':
            content.setlist('gender', '')

        self.request.POST = content
        if self.form_valid:
            obj_user = DataBaseUser.objects.get(pk=kwargs['pk'])
            # Формируем словарь записей, которые будем записывать, поля job и division обрабатываем отдельно
            work_kwargs = {
                'date_of_employment': content['date_of_employment'] if content['date_of_employment'] != '' else None,
                'internal_phone': content['internal_phone'],
                'work_email_password': content['work_email_password'],
                'work_application_password': content['work_application_password'],
                'personal_work_schedule_start': content['personal_work_schedule_start'],
                'personal_work_schedule_end': content['personal_work_schedule_end'],
            }
            # Формируем словарь записей, которые будем записывать, поля citizenship и passport обрабатываем отдельно
            personal_kwargs = {
                'snils': content['snils'],
                'oms': content['oms'],
                'inn': content['inn'],
            }
            identity_documents_kwargs = {
                'series': content['series'],
                'number': content['number'],
                'issued_by_whom': content['issued_by_whom'],
                'date_of_issue': content['date_of_issue'] if content['date_of_issue'] != '' else None,
                'division_code': content['division_code'],
            }
            # Если поле job не является пустым, расширяем словарь. То же самое делем с division
            if content['job'] != 'none':
                work_kwargs['job'] = Job.objects.get(pk=content['job'])
            if content['divisions'] != 'none':
                work_kwargs['divisions'] = Division.objects.get(pk=content['divisions'])
            if content['citizenship'] != 'none':
                personal_kwargs['citizenship'] = Citizenships.objects.get(pk=content['citizenship'])
            if not obj_user.user_work_profile:
                obj_work_profile = DataBaseUserWorkProfile(**work_kwargs)
                with transaction.atomic():
                    obj_work_profile.save()
                obj_user.user_work_profile = obj_work_profile
            else:
                obj_work_profile = DataBaseUserWorkProfile.objects.get(pk=obj_user.user_work_profile.pk)
                # Если поле job или division пришли пустыми, присваиваем None значению поля и сохраняем
                if content['job'] == 'none':
                    obj_work_profile.job = None
                    with transaction.atomic():
                        obj_work_profile.save()
                if content['divisions'] == 'none':
                    obj_work_profile.divisions = None
                    with transaction.atomic():
                        obj_work_profile.save()
                obj_work_profile = DataBaseUserWorkProfile.objects.filter(pk=obj_user.user_work_profile.pk)
                obj_work_profile.update(**work_kwargs)

            if not obj_user.user_profile:
                obj_personal_profile_identity_documents = IdentityDocuments(**identity_documents_kwargs)
                with transaction.atomic():
                    obj_personal_profile_identity_documents.save()
                personal_kwargs['passport'] = obj_personal_profile_identity_documents
                obj_personal_profile = UserProfile(**personal_kwargs)
                with transaction.atomic():
                    obj_personal_profile.save()
                obj_user.user_profile = obj_personal_profile
            else:
                try:
                    obj_personal_profile = UserProfile.objects.get(pk=obj_user.user_profile.pk)
                    try:
                        obj_personal_profile_identity_documents = IdentityDocuments.objects.filter(
                            pk=obj_personal_profile.passport.pk)
                        obj_personal_profile_identity_documents.update(**identity_documents_kwargs)
                    except Exception as _ex:
                        message = f'Ошибка сохранения профиля. У пользователя |{obj_user.username}| отсутствует данные паспорта!!!: {_ex}'
                        logger.error(message)
                    if content['citizenship'] == 'none':
                        obj_personal_profile.citizenship = None
                        with transaction.atomic():
                            obj_personal_profile.save()
                    obj_personal_profile = UserProfile.objects.filter(pk=obj_user.user_profile.pk)
                    obj_personal_profile.update(**personal_kwargs)
                except Exception as _ex:
                    message = f'Ошибка сохранения профиля. У пользователя |{obj_user.username}| отсутствует личный профиль!!!: {_ex}'
                    logger.error(message)
            with transaction.atomic():
                obj_user.save()
        return super(StaffUpdate, self).post(request, *args, **kwargs)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Подразделения: Список, Добавление, Детализация, Обновление
"""


class DivisionsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Division
    template_name = 'customers_app/divisions_list.html'
    permission_required = 'customers_app.view_division'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            divisions_list = Division.objects.filter(active=True)
            data = [divisions_item.get_data() for divisions_item in divisions_list]
            response = {'data': data}
            return JsonResponse(response)
        count = 0
        if self.request.GET:
            todos = get_jsons_data("Catalog", "ПодразделенияОрганизаций", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Description'] != "":
                    parent_category = True if Division.objects.filter(
                        ref_key=item['Parent_Key']).count() == 1 else False
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'parent_category': Division.objects.get(
                            ref_key=item['Parent_Key']) if parent_category else None,
                        'code': item['Code'],
                        'name': item['Description'],
                        'description': item['Description'],
                        'history': datetime.datetime.strptime(item['ДатаСоздания'][:10], "%Y-%m-%d"),
                        'okved': item['КодОКВЭД2'],
                        'active': False if item['Расформировано'] else True,
                    }
                    Division.objects.update_or_create(ref_key=item['Ref_Key'], defaults=divisions_kwargs)
                    # db_instance = Division(**divisions_kwargs)
                    # db_instance.save()
                    # count += 1
            all_divisions = Division.objects.filter(parent_category=None)
            for item in todos['value']:
                if item['Description'] != "" and item['Parent_Key'] != "00000000-0000-0000-0000-000000000000":
                    if all_divisions.filter(ref_key=item['Ref_Key']).count() == 1:
                        division = Division.objects.get(ref_key=item['Ref_Key'])
                        division.parent_category = Division.objects.get(ref_key=item['Parent_Key'])
                        with transaction.atomic():
                            division.save()
            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:divisions_list')
            return redirect(url_match)

        return super(DivisionsList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Division.objects.filter(active=True).order_by('code')
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Подразделения'
        return context


class DivisionsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Division
    form_class = DivisionsAddForm
    template_name = 'customers_app/divisions_add.html'
    permission_required = 'customers_app.add_division'

    def get_context_data(self, **kwargs):
        content = super(DivisionsAdd, self).get_context_data(**kwargs)
        content['all_divisions'] = Division.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(DivisionsAdd, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            content = QueryDict.copy(self.request.POST)
            content['history'] = datetime.datetime.now()
            if content['parent_category'] == 'none':
                content.setlist('parent_category', '')
            self.request.POST = content
        return super(DivisionsAdd, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:divisions_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class DivisionsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Division
    template_name = 'customers_app/divisions_detail.html'
    permission_required = 'customers_app.view_division'


class DivisionsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Division
    template_name = 'customers_app/divisions_update.html'
    form_class = DivisionsUpdateForm
    permission_required = 'customers_app.change_division'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(reverse('customers_app:login'))
        return super(DivisionsUpdate, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super(DivisionsUpdate, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            content = QueryDict.copy(self.request.POST)
            content['active'] = boolean_return(request, 'active')
            if content['parent_category'] == 'none':
                content.setlist('parent_category', '')
            self.request.POST = content
        return super(DivisionsUpdate, self).post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        content = super(DivisionsUpdate, self).get_context_data(**kwargs)
        content['all_divisions'] = Division.objects.all()
        return content

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:divisions', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Должности: Список, Добавление, Детализация, Обновление
"""


class JobsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Job
    template_name = 'customers_app/jobs_list.html'
    item_sorted = 'pk'
    sorted_list = ['pk', 'code', 'name', 'date_entry']
    permission_required = 'customers_app.view_job'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            job_list = Job.objects.filter(excluded_standard_spelling=False)
            data = [job_item.get_data() for job_item in job_list]
            response = {'data': data}
            return JsonResponse(response)
        count = 0
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "Должности", 0)
            todos2 = get_jsons_data("Catalog", "ТрудовыеФункции", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Description'] != "" and item['ВведенаВШтатноеРасписание']:
                    jobs_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'code': '',
                        'name': item['Description'],
                        'date_entry': datetime.datetime.strptime(item['ДатаВвода'][:10], "%Y-%m-%d"),
                        'employment_function': item['ТрудоваяФункция_Key'],
                        'date_exclusions': datetime.datetime.strptime(item['ДатаИсключения'][:10], "%Y-%m-%d"),
                        'excluded_standard_spelling': item['ИсключенаИзШтатногоРасписания']
                    }
                    Job.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**jobs_kwargs})
                    # db_instance = Job(**jobs_kwargs)
                    # db_instance.save()
                    # count += 1
            for item in todos2['value']:
                object_list = Job.objects.filter(employment_function=item['Ref_Key'])
                for unit in object_list:
                    unit.code = item['ОКПДТРКод']
                    with transaction.atomic():
                        unit.save()

            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)

        return super(JobsList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Job.objects.filter(excluded_standard_spelling=False).order_by(self.item_sorted)
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(JobsList, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Должности'
        change_session_context(context, self)
        return context


class JobsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Job
    form_class = JobsAddForm
    template_name = 'customers_app/jobs_add.html'
    permission_required = 'customers_app.add_job'

    def get_context_data(self, **kwargs):
        content = super(JobsAdd, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(JobsAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class JobsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Job
    template_name = 'customers_app/jobs_detail.html'
    permission_required = 'customers_app.view_job'


class JobsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Job
    template_name = 'customers_app/jobs_update.html'
    form_class = JobsUpdateForm
    permission_required = 'customers_app.change_job'
    success_url = 'customers_app:jobs_list'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return redirect(reverse('customers_app:login'))
        return super(JobsUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        content = super(JobsUpdate, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(JobsUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Вредные условия труда: Список, Добавление, Детализация, Обновление
"""


class HarmfulWorkingConditionsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = HarmfulWorkingConditions
    permission_required = 'customers_app.view_harmfulworkingconditions'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            harmful_list = HarmfulWorkingConditions.objects.all()
            data = [harmful_item.get_data() for harmful_item in harmful_list]
            response = {'data': data}
            return JsonResponse(response)
        count = 0
        if self.request.GET:
            todos = get_jsons_data("Catalog", "ВредныеОпасныеПроизводственныеФакторыИВыполняемыеРаботы", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['IsFolder'] != True:
                    harmful_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'code': item['Code'],
                        'name': item['Description'],
                        'frequency_inspection': item['ПериодичностьОсмотра'],
                        'frequency_multiplicity': item['КратностьОсмотра'],
                    }
                    if HarmfulWorkingConditions.objects.filter(ref_key=item['Ref_Key']).count() != 1:
                        db_instance = HarmfulWorkingConditions(**harmful_kwargs)
                        with transaction.atomic():
                            db_instance.save()
                        count += 1

            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:harmfuls_list')
            return redirect(url_match)
        return super(HarmfulWorkingConditionsList, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Вредные условия труда'
        return context


class CounteragentDocumentsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = CounteragentDocuments
    permission_required = "customers_app.view_counteragentdocuments"

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            purpose_list = CounteragentDocuments.objects.all()
            data = [purpose_item.get_data() for purpose_item in purpose_list]
            response = {"data": data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Документы контрагентов"
        return context


class CounteragentDocumentsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = CounteragentDocuments
    form_class = CounteragentDocumentsAddForm
    permission_required = "customers_app.add_counteragentdocuments"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Добавить документ контрагента"
        return context

    def form_valid(self, form):
        if form.is_valid():
            refresh_form = form.save(commit=False)
            if refresh_form.description == '':
                filename = str(refresh_form.document)
                refresh_form.description = filename.split('/')[-1]
            refresh_form.save()
        return super().form_valid(form)


class CounteragentDocumentsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = CounteragentDocuments
    form_class = CounteragentDocumentsUpdateForm
    permission_required = "customers_app.change_counteragentdocuments"
    template_name = 'customers_app/counteragentdocuments_form_update.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}"
        return context

    def form_valid(self, form):
        if form.is_valid():
            refresh_form = form.save(commit=False)
            if refresh_form.description == '':
                filename = str(refresh_form.document)
                refresh_form.description = filename.split('/')[-1]
            refresh_form.save()
        return super().form_valid(form)


@login_required
def generate_config_file(request):
    try:
        user = request.user  # Получаем текущего пользователя

        # Если ваш пользователь не связан напрямую с базовой моделью пользователя Django,
        # вам нужно будет получить его через связь, например:
        # db_user = get_object_or_404(DataBaseUser, ref_key=user.ref_key)

        db_user = get_object_or_404(DataBaseUser, pk=user.pk)  # Пример получения объекта по email

        # Определите контекст для замены плейсхолдеров
        context = {
            'ref_key': db_user.ref_key,
            'email': db_user.email,
            'title': db_user.title,
            'job': db_user.user_work_profile.job.name,
            'sign': FIO_format(db_user.title),
        }

        # Загрузите шаблон XML
        xml_content = render_to_string('customers_app/k9settings_template.xml', context)

        # Сформируйте имя файла на основе ref_key
        filename = f'thunderbird_settings_{db_user.ref_key}.k9s'

        # Создайте ответ для скачивания файла
        response = HttpResponse(xml_content, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
    except Exception as e:
        logger.error(f'Error generating K9 settings file: {e}')
        return HttpResponse(status=404, content=f'Error generating K9 settings file: {e}')
    return response


def generate_employee_file(request, pk):
    db_user = get_object_or_404(DataBaseUser, pk=pk)

    # Создаем текстовый файл
    file_content = ""
    file_content += "\n" + "=" * 50 + "\n\n"
    file_content += f"ФИО работника: {db_user.title}\n"
    file_content += f"Должность: {db_user.user_work_profile.job.name}\n"
    file_content += "\n" + "=" * 50 + "\n\n"
    file_content += f"Корпоративный сайт\n"
    file_content += f"URL корпоративного сайта: https://corp.barkol.ru/\n"
    file_content += f"Логин для корпоративного сайта: {db_user.username}\n"
    file_content += f"Пароль для корпоративного сайта: {db_user.user_work_profile.work_email_password}\n"
    file_content += "\n" + "=" * 50 + "\n\n"
    file_content += f"Электронная почта\n"
    file_content += f"URL для доступа к электронной почте: https://ms.barkol.ru/\n"
    file_content += f"Логин для электронной почты: {db_user.email}\n"
    file_content += f"Пароль для электронной почты: {db_user.user_work_profile.work_email_password}\n"
    file_content += "\n" + "=" * 50 + "\n\n"
    file_content += f"Параметры для ручной настройки почтовых клиентов\n"
    file_content += f"Входящий сервер (IMAP): imap.barkol.ru\n"
    file_content += f"Порт входящего сервера: 993\n"
    file_content += f"Защита соединения: SSL/TLS\n"
    file_content += f"Исходящий сервер (SMTP): sm.barkol.ru\n"
    file_content += f"Порт исходящего сервера: 465\n"
    file_content += f"Защита соединения: SSL/TLS\n"
    file_content += "\n" + "=" * 50 + "\n\n"

    # Возвращаем файл как HTTP-ответ
    response = HttpResponse(file_content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{db_user.username}_credentials.txt"'
    return response


@login_required
def game(request):
    return render(request, 'customers_app/tetris.html')


@csrf_exempt  # Уберите этот декоратор в production
def save_stats(request):
    if request.method == 'POST':
        try:
            # Чтение JSON-данных из тела запроса
            data = json.loads(request.body)
            score = data.get('score')
            level = data.get('level')
            lines_cleared = data.get('lines_cleared')

            # Проверка, что все данные присутствуют
            if score is None or level is None or lines_cleared is None:
                return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

            # Преобразование данных в числа
            score = int(score)
            level = int(level)
            lines_cleared = int(lines_cleared)

            # Сохранение статистики
            stats = UserStats.objects.create(
                user=request.user,
                score=score,
                level=level,
                lines_cleared=lines_cleared
            )
            stats.save()

            return JsonResponse({'status': 'success'})
        except (ValueError, json.JSONDecodeError) as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def get_leaderboard(request):
    if request.method == 'GET':
        try:
            # Общий победитель (пользователь с максимальным счетом)
            overall_winner = UserStats.objects.order_by('-score').first()
            overall_winner_data = {
                'username': overall_winner.user.title if overall_winner else None,
                'score': overall_winner.score if overall_winner else 0,
            }

            # Лучший результат текущего пользователя
            user_best = None
            if request.user.is_authenticated:
                user_best = UserStats.objects.filter(user=request.user).order_by('-score').first()

            user_best_data = {
                'score': user_best.score if user_best else 0,
            }

            return JsonResponse({
                'overall_winner': overall_winner_data,
                'user_best': user_best_data,
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

@login_required
def inactive_users_report(request):
    """
    Генерирует отчет о пользователях, которые никогда не входили в систему.

    Фильтрует пользователей с `last_login = NULL`, выбирает связанную информацию о работе,
    группирует пользователей по типу работы и передает данные в шаблон.

    Returns:
        HttpResponse: Отрендеренный HTML-шаблон с данными.
    """

    # Словарь для отображения ключевых значений типов работ в человекочитаемые названия
    JOB_TYPE_DISPLAY = dict(Job.job_type)

    # Запрос: активные пользователи, которые никогда не логинились
    queryset = (
        DataBaseUser.objects
        .filter(last_login__isnull=True)
        .select_related('user_work_profile__job')  # Оптимизация: загрузка связанных объектов
        .annotate(
            full_name=F('last_name'),
            job_name=F('user_work_profile__job__name'),
            job_type=F('user_work_profile__job__type_of_job'),
            registration_date=F('date_joined')
        )
        .exclude(is_active=False)  # Исключаем неактивных пользователей
    )

    # Итоговые данные для отчета — словарь: {тип работы: [пользователь1, пользователь2, ...]}
    report_data = defaultdict(list)

    for user in queryset:
        job_type_key = user.job_type
        job_type_display = JOB_TYPE_DISPLAY.get(job_type_key, 'Не указано')

        report_data[job_type_display].append({
            'full_name': f"{user.last_name} {user.first_name} {user.surname}".strip(),
            'registration_date': user.registration_date,
            'job_name': user.job_name or '—',
        })

    return render(request, 'customers_app/inactive_users.html', {'report': dict(report_data)})
