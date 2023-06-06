import datetime
import json

import requests
from dateutil import rrule
from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse

from django.views.generic import ListView
from loguru import logger

from administration_app.models import PortalProperty
from administration_app.utils import get_users_info, change_users_password, get_jsons_data_filter, get_jsons_data, \
    get_jsons_data_filter2, get_types_userworktime, get_date_interval
from customers_app.models import DataBaseUser, Groups, Job
from hrdepartment_app.models import OfficialMemo, WeekendDay, ReportCard, TypesUserworktime, check_day
from hrdepartment_app.tasks import report_card_separator, report_card_separator_loc

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# Create your views here.

def index(request):
    pass


def get_sick_leave(year):
    """
    Получение больничных листов в 1с
    :param year: Год, за который запрашиваем информацию.
    :return:
    """
    url = f'http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27Болезнь%27'
    source_url = url
    try:
        response = requests.get(source_url, auth=(config('HRM_LOGIN'), config('HRM_PASS')))
        dt = json.loads(response.text)
        rec_number_count = 0
        for item in dt['value']:
            if item['Recorder_Type'] == 'StandardODATA.Document_БольничныйЛист':
                interval = get_date_interval(datetime.datetime.strptime(item['Начало'][:10], "%Y-%m-%d"),
                                             datetime.datetime.strptime(item['Окончание'][:10], "%Y-%m-%d"))
                rec_list = ReportCard.objects.filter(doc_ref_key=item['ДокументОснование'])
                for record in rec_list:
                    record.delete()
                try:
                    user_obj = DataBaseUser.objects.get(ref_key=item['Сотрудник_Key'])
                    for date in interval:
                        rec_number_count += 1
                        start_time, end_time = check_day(date, datetime.datetime(1, 1, 1, 9, 30).time(),
                                                         datetime.datetime(1, 1, 1, 18, 0).time())
                        kwargs_obj = {
                            'report_card_day': date,
                            'employee': user_obj,
                            'rec_no': rec_number_count,
                            'doc_ref_key': item['ДокументОснование'],
                            'record_type': '16',
                            'reason_adjustment': 'Запись введена автоматически из 1С ЗУП',
                            'start_time': start_time,
                            'end_time': end_time,
                        }
                        ReportCard.objects.update_or_create(report_card_day=date, doc_ref_key=item['ДокументОснование'],
                                                            defaults=kwargs_obj)
                        print(kwargs_obj)
                except Exception as _ex:
                    logger.error(f"{item['Сотрудник_Key']} не найден в базе данных")
    except Exception as _ex:
        logger.debug(f'{_ex}')
        return {'value': ""}



class PortalPropertyList(LoginRequiredMixin, ListView):
    model = PortalProperty

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['Group'] = Groups.objects.all()
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Настройки портала'
        return context

    def get(self, request, *args, **kwargs):
        if self.request.user.is_superuser:
            # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                property_list = PortalProperty.objects.all()
                data = [property_item.get_data() for property_item in property_list]
                response = {'data': data}
                return JsonResponse(response)
            # Установка общих прав пользователя наследованием из групп
            if request.GET.get('update') == '0':
                group_list = [unit for unit in Groups.objects.filter(name__contains='Общая')]
                job_list = Job.objects.all()
                for item in job_list:
                    for unit in group_list:
                        item.group.add(unit.id)
            # Установка прав пользователя наследованием из групп
            if request.GET.get('update') == '1':
                users_list = DataBaseUser.objects.all().exclude(username='proxmox', is_active=False)
                for user_obj in users_list:
                    try:
                        user_obj.groups.clear()
                        for item in user_obj.user_work_profile.job.group.all():
                            user_obj.groups.add(item)
                        user_obj.save()
                    except AttributeError:
                        logger.info(f"У пользователя {user_obj} отсутствуют группы!")
                        # Установка общих прав пользователя наследованием из групп
            if request.GET.get('update') == '2':
                memo_list = OfficialMemo.objects.all()
                for item in memo_list:
                    if item.title == '':
                        item.save()
            if request.GET.get('update') == '3':
                get_sick_leave(2022)
            if request.GET.get('update') == '4':
                # report_card_separator_loc()
                dt = get_types_userworktime()
                for item in dt['value']:
                    # print(value)
                    kwargs_obj = {
                        'ref_key': item['Ref_Key'],
                        'description': item['Description'],
                        'letter_code': item['БуквенныйКод'],
                        'active': False,
                    }
                    TypesUserworktime.objects.update_or_create(ref_key=item['Ref_Key'], defaults=kwargs_obj)
            if request.GET.get('update') == '5':
                type_of_report = {
                    '2': 'Ежегодный',
                    '3': 'Дополнительный ежегодный отпуск',
                    '4': 'Отпуск за свой счет',
                    '5': 'Дополнительный учебный отпуск (оплачиваемый)',
                    '6': 'Отпуск по уходу за ребенком',
                    '7': 'Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС',
                    '8': 'Отпуск по беременности и родам',
                    '9': 'Отпуск без оплаты согласно ТК РФ',
                    '10': 'Дополнительный отпуск',
                    '11': 'Дополнительный оплачиваемый отпуск пострадавшим в ',
                    '12': 'Основной',
                }
                exclude_list = ['proxmox', 'shakirov']
                for item in DataBaseUser.objects.all().exclude(username__in=exclude_list).values('ref_key'):
                    print(item['ref_key'])
                    dt = get_jsons_data_filter2('InformationRegister', 'ДанныеОтпусковКарточкиСотрудника', 'Сотрудник_Key',
                                                item['ref_key'], 'year(ДатаОкончания)', 2020, 0, 0)
                    for key in dt:
                        for item in dt[key]:
                            usr_obj = DataBaseUser.objects.get(ref_key=item['Сотрудник_Key'])
                            start_date = datetime.datetime.strptime(item['ДатаНачала'][:10], "%Y-%m-%d")
                            end_date = datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d")
                            weekend_count = WeekendDay.objects.filter(
                                Q(weekend_day__gte=start_date) & Q(weekend_day__lte=end_date) & Q(weekend_type='1')).count()
                            count_date = int(item['КоличествоДней']) + weekend_count
                            period = list(rrule.rrule(rrule.DAILY, count=count_date, dtstart=start_date))
                            weekend = [item.weekend_day for item in WeekendDay.objects.filter(
                                Q(weekend_day__gte=start_date.date()) & Q(weekend_day__lte=end_date.date()))]
                            for unit in period:
                                if unit.weekday() in [0, 1, 2, 3] and unit.date() not in weekend:
                                    delta_time = datetime.timedelta(
                                        hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                                        minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute)
                                    start_time = usr_obj.user_work_profile.personal_work_schedule_start
                                    end_time = datetime.datetime.strptime(str(delta_time), '%H:%M:%S').time()
                                elif unit.weekday() == 4 and unit not in weekend:
                                    delta_time = datetime.timedelta(
                                        hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                                        minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute) - \
                                                 datetime.timedelta(hours=1)
                                    start_time = usr_obj.user_work_profile.personal_work_schedule_start
                                    end_time = datetime.datetime.strptime(str(delta_time), '%H:%M:%S').time()
                                else:
                                    start_time = datetime.datetime.strptime('00:00:00', '%H:%M:%S').time()
                                    end_time = datetime.datetime.strptime('00:00:00', '%H:%M:%S').time()

                                value = [i for i in type_of_report if type_of_report[i] == item['ВидОтпускаПредставление']]
                                kwargs_obj = {
                                    'report_card_day': unit,
                                    'employee': usr_obj,
                                    'start_time': start_time,
                                    'end_time': end_time,
                                    'reason_adjustment': item['Основание'],
                                    'doc_ref_key': item['ДокументОснование'],
                                }
                                ReportCard.objects.update_or_create(report_card_day=unit, employee=usr_obj, record_type=value[0],
                                                                    defaults=kwargs_obj)

        return super().get(request, *args, **kwargs)
