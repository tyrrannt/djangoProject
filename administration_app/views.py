import datetime
import json

import requests
from dateutil import rrule
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse

from django.views.generic import ListView
from loguru import logger

from administration_app.models import PortalProperty
from administration_app.utils import get_users_info, change_users_password, get_jsons_data_filter, get_jsons_data, \
    get_jsons_data_filter2
from customers_app.models import DataBaseUser, Groups, Job
from hrdepartment_app.models import OfficialMemo, WeekendDay, ReportCard
from hrdepartment_app.tasks import report_card_separator, report_card_separator_loc

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


# Create your views here.

def index(request):
    pass


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
                get_users_info()
            if request.GET.get('update') == '4':
                # change_users_password()
                # current_data = datetime.datetime.date(datetime.datetime.today())
                current_data1 = datetime.datetime.date(datetime.datetime(2020, 1, 1))
                current_data2 = datetime.datetime.date(datetime.datetime(2020, 12, 31))
                url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data1}&enddate={current_data2}"
                source_url = url
                try:
                    response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
                except Exception as _ex:
                    return f"{_ex} ошибка"
                dicts = json.loads(response.text)
                for item in dicts['data']:
                    usr = item['FULLNAME']
                    current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
                    start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
                    end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
                    rec_no = int(item['rec_no'])
                    search_user = usr.split(' ')
                    try:
                        user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                            surname=search_user[2])
                        kwargs = {
                            'report_card_day': current_data,
                            'rec_no': rec_no,
                            'employee': user_obj,
                            'start_time': start_time,
                            'end_time': end_time,
                            'record_type': '1',
                        }
                        ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj,
                                                            defaults=kwargs)
                    except Exception as _ex:
                        logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")
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
