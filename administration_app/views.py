import csv
import datetime
import json

from django.contrib.auth.decorators import login_required
from django.utils.datastructures import MultiValueDictKeyError
import requests
from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from django.views.generic import ListView
from loguru import logger

from administration_app.models import PortalProperty
from contracts_app.models import Contract

from customers_app.models import DataBaseUser, Groups, Job, AccessLevel
from hrdepartment_app.models import ReportCard
from hrdepartment_app.tasks import get_sick_leave, birthday_telegram, upload_json, get_vacation, get_year_report, \
    save_report, send_email_notification, vacation_schedule_send, vacation_check

logger.add("debug_administration.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
           rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
           serialize=config('LOG_SERIALIZE'))



# Create your views here.

def index(request):
    pass


# def get_sick_leave(year, triger):
#     """
#     Получение неявок на рабочее место.
#     :param year: Год, за который запрашиваем информацию.
#     :param triger: 1 - больничные, 2 - мед осмотры.
#     :return:
#     """
#     if triger == 1:
#         url = f'http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20Состояние%20eq%20%27Болезнь%27'
#         triger_type = 'StandardODATA.Document_БольничныйЛист'
#         record_type = '16'
#     if triger == 2:
#         url = f'http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДанныеСостоянийСотрудников_RecordType?$format=application/json;odata=nometadata&$filter=year(Окончание)%20eq%20{year}%20and%20ВидВремени_Key%20eq%20guid%27e58f3899-3c5b-11ea-a186-0cc47a7917f4%27'
#         triger_type = 'StandardODATA.Document_ОплатаПоСреднемуЗаработку'
#         record_type = '17'
#
#     source_url = url
#     try:
#         response = requests.get(source_url, auth=(config('HRM_LOGIN'), config('HRM_PASS')))
#         dt = json.loads(response.text)
#         rec_number_count = 0
#         for item in dt['value']:
#             if item['Recorder_Type'] == triger_type and item['Active'] == True:
#                 interval = get_date_interval(datetime.datetime.strptime(item['Начало'][:10], "%Y-%m-%d"),
#                                              datetime.datetime.strptime(item['Окончание'][:10], "%Y-%m-%d"))
#                 rec_list = ReportCard.objects.filter(doc_ref_key=item['ДокументОснование'])
#                 for record in rec_list:
#                     record.delete()
#                 try:
#                     user_obj = DataBaseUser.objects.get(ref_key=item['Сотрудник_Key'])
#                     for date in interval:
#                         rec_number_count += 1
#                         start_time, end_time = check_day(date, datetime.datetime(1, 1, 1, 9, 30).time(),
#                                                          datetime.datetime(1, 1, 1, 18, 0).time())
#                         kwargs_obj = {
#                             'report_card_day': date,
#                             'employee': user_obj,
#                             'rec_no': rec_number_count,
#                             'doc_ref_key': item['ДокументОснование'],
#                             'record_type': record_type,
#                             'reason_adjustment': 'Запись введена автоматически из 1С ЗУП',
#                             'start_time': start_time,
#                             'end_time': end_time,
#                         }
#                         ReportCard.objects.update_or_create(report_card_day=date, doc_ref_key=item['ДокументОснование'],
#                                                             defaults=kwargs_obj)
#                         print(kwargs_obj)
#                 except Exception as _ex:
#                     logger.error(f"{item['Сотрудник_Key']} не найден в базе данных")
#     except Exception as _ex:
#         logger.debug(f'{_ex}')
#         return {'value': ""}

def import_data(request):
    error = {'error': ''}
    try:
        if request.method == 'POST' and request.FILES['json_file']:
            trigger = 2
            if request.POST.get('contragent') == "on":
                trigger = 0
            if request.POST.get('contract') == "on":
                trigger = 1
            json_file = request.FILES['json_file']
            dt = json.load(json_file)
            upload_json.delay(dt, trigger)
            error = {
                'error': 'Данные отправлены на сервер для загрузки. Результат загрузки можно посмотреть в файле debug.json'}
            return render(request, 'administration_app/success.html', context=error)
    except MultiValueDictKeyError:
        error = {'error': 'Не выбран файл'}
        return render(request, 'administration_app/json.html', context=error)
    return render(request, 'administration_app/json.html', context=error)


def export_users_to_csv(file_path):
    # Открываем файл для записи
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, delimiter=';')

        # Записываем заголовки
        headers = [
            "Name", "FullName", "Description", "Enable", "DataSource", "Authentication",
            "Role", "Groups", "MailAddress", "EmailForwarding", "ItemLimit", "DiskSizeLimit (kB)",
            "ConsumedItems", "ConsumedSize (kB)", "OutgoingMessageLimit (kB)", "LastLogin (UTC)",
            "PublishInGAL", "CleanOutItems", "DomainRestriction"
        ]
        writer.writerow(headers)

        # Получаем данные из модели DataBaseUser
        users = DataBaseUser.objects.all()

        # Записываем данные для каждого пользователя
        for user in users:
            email = user.email.split('@')[0] if user.email else ''
            full_name = user.get_title()

            row = [
                email,  # Name
                full_name,  # FullName
                "",  # Description
                "Yes",  # Enable
                "Internal",  # DataSource
                "Internal",  # Authentication
                "No rights",  # Role
                "",  # Groups
                email,  # MailAddress
                "",  # EmailForwarding
                "",  # ItemLimit
                "",  # DiskSizeLimit (kB)
                "",  # ConsumedItems
                "",  # ConsumedSize (kB)
                "",  # OutgoingMessageLimit (kB)
                "",  # LastLogin (UTC)
                "Yes",  # PublishInGAL
                "Domain defined",  # CleanOutItems
                "No"  # DomainRestriction
            ]
            writer.writerow(row)

    # error = {'error': ''}
    # updated = 0
    # create = 0
    # if request.POST.get('contragent') == "on":
    #     try:
    #         if request.method == 'POST' and request.FILES['json_file']:
    #             json_file = request.FILES['json_file']
    #             data = json.load(json_file)
    #             for item in data:
    #                 counteragent = {
    #                     "ref_key": item['fields']['ref_key'],
    #                     "short_name": item['fields']['short_name'] if item['fields']['short_name'] else '',
    #                     "full_name": item['fields']['full_name'],
    #                     "inn": item['fields']['inn'],
    #                     "kpp": item['fields']['kpp'] if item['fields']['kpp'] else '',
    #                     "ogrn": item['fields']['ogrn'],
    #                     "type_counteragent": item['fields']['type_counteragent'],
    #                     "juridical_address": item['fields']['juridical_address'],
    #                     "physical_address": item['fields']['physical_address'],
    #                     "email": item['fields']['email'] if item['fields']['email'] else '',
    #                     "phone": item['fields']['phone'] if item['fields']['phone'] else '',
    #                     "base_counteragent": item['fields']['base_counteragent'],
    #                     "director": item['fields']['director'],
    #                     "accountant": item['fields']['accountant'],
    #                     "contact_person": item['fields']['contact_person'],
    #                 }
    #                 try:
    #                     obj, created = Counteragent.objects.update_or_create(inn=item['fields']['inn'],
    #                                                                          kpp=item['fields']['kpp'],
    #                                                                          defaults=counteragent)
    #                     if created:
    #                         create += 1
    #                     else:
    #                         updated += 1
    #                 except MultipleObjectsReturned:
    #                     error[
    #                         'error'] += f"Найдено нескольких объектов в базе данных с таким {item['fields']['inn']} \n"
    #             error['updated'] = updated
    #             error['created'] = create
    #             return render(request, 'administration_app/success.html', context=error)
    #     except MultiValueDictKeyError:
    #         error = {'error': 'Не выбран файл'}
    #         return render(request, 'administration_app/json.html', context=error)
    # if request.POST.get('contract') == "on":
    #     try:
    #         if request.method == 'POST' and request.FILES['json_file']:
    #             json_file = request.FILES['json_file']
    #             data = json.load(json_file)
    #             for item in data:
    #                 contract = {
    #                     "contract_counteragent_id": int(item['contract_counteragent']),
    #                     "contract_number": item['contract_number'],
    #                     "date_conclusion": item['date_conclusion'] if item['date_conclusion'] else None,
    #                     "subject_contract": item['subject_contract'],
    #                     "cost": float(item['cost']) if item['cost'] else 0,
    #                     "type_of_contract_id": item['type_of_contract'],
    #                     "type_of_document_id": item['type_of_document'],
    #                     "closing_date": item['closing_date'] if item['closing_date'] else None,
    #                     "prolongation": item['prolongation'],
    #                     "comment": item['comment'],
    #                     "date_entry": item['date_entry'] if item['date_entry'] else None,
    #                     "executor_id": item['executor'],
    #                     "doc_file": item['doc_file'],
    #                     "access_id": item['access'],
    #                     "allowed_placed": item['allowed_placed'],
    #                     "actuality": item['actuality'],
    #                     "official_information": item['official_information'],
    #
    #                 }
    #                 try:
    #                     # counteragent = Counteragent.objects.get(pk=item['contract_counteragent'])
    #                     # print(counteragent)
    #                     # new_obj = Contract(**contract)
    #                     # new_obj.save()
    #                     obj, created = Contract.objects.update_or_create(
    #                         contract_counteragent_id=item['contract_counteragent'],
    #                         contract_number=item['contract_number'],
    #                         date_conclusion=item['date_conclusion'],
    #                         defaults=contract)
    #                     if created:
    #                         if len(item['divisions']) > 0:
    #                             obj.divisions.set(item['divisions'])
    #                         if len(item['type_property']) > 0:
    #                             obj.type_property.set(item['type_property'])
    #                         if len(item['employee']) > 0:
    #                             obj.employee.set(item['employee'])
    #                         # obj.save()
    #                         create += 1
    #                     else:
    #                         updated += 1
    #                 except MultipleObjectsReturned:
    #                     error[
    #                         'error'] += f"Найдено нескольких объектов в базе данных с таким {item['fields']['inn']} \n"
    #             error['updated'] = updated
    #             error['created'] = create
    #             return render(request, 'administration_app/success.html', context=error)
    #     except MultiValueDictKeyError:
    #         error = {'error': 'Не выбран файл'}
    #         return render(request, 'administration_app/json.html', context=error)

    # return render(request, 'administration_app/json.html')


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
            # Обновить заголовки СЗ
            if request.GET.get('update') == '2':
                users_list = DataBaseUser.objects.all().exclude(is_superuser=True)
                user_access = AccessLevel.objects.get(level=3)
                for item in users_list:
                    item.user_access = user_access
                    item.save()
                # memo_list = OfficialMemo.objects.all()
                # for item in memo_list:
                #     if item.title == '':
                #         item.save()
            if request.GET.get('update') == '3':
                control_date = request.GET.get('control_date')
                if control_date:
                    current_data = datetime.datetime.strptime(control_date, '%Y-%m-%d').date()
                else:
                    current_data = datetime.datetime.today().date()
                rec_obj = ReportCard.objects.filter(Q(report_card_day=current_data) & Q(record_type='1'))
                for item in rec_obj:
                    print(item)
                    item.delete()
                # current_data1 = datetime.datetime.date(datetime.datetime(2023, 1, 1))
                # current_data2 = datetime.datetime.date(datetime.datetime(2023, 5, 25))
                url = f"http://192.168.10.233:5053/api/time/intervals?startdate={current_data}&enddate={current_data}"
                source_url = url
                try:
                    response = requests.get(source_url, auth=('proxmox', 'PDO#rLv@Server'))
                except Exception as _ex:
                    return f"{_ex} ошибка"
                dicts = json.loads(response.text)
                for item in dicts['data']:
                    usr = item['FULLNAME']
                    # current_data = datetime.datetime.strptime(item['STARTDATE'], "%d.%m.%Y").date()
                    current_intervals = True if item['ISGO'] == '0' else False
                    start_time = datetime.datetime.strptime(item['STARTTIME'], "%d.%m.%Y %H:%M:%S").time()
                    if current_intervals:
                        end_time = datetime.datetime.strptime(item['ENDTIME'], "%d.%m.%Y %H:%M:%S").time()
                    else:
                        end_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    rec_no = int(item['rec_no'])

                    search_user = usr.split(' ')
                    try:
                        user_obj = DataBaseUser.objects.get(last_name=search_user[0], first_name=search_user[1],
                                                            surname=search_user[2])
                        kwargs = {
                            'report_card_day': current_data,
                            'employee': user_obj,
                            'start_time': start_time,
                            'end_time': end_time,
                            'record_type': '1',
                            'current_intervals': current_intervals,
                        }
                        ReportCard.objects.update_or_create(report_card_day=current_data, employee=user_obj,
                                                            rec_no=rec_no,
                                                            defaults=kwargs)
                    except Exception as _ex:
                        logger.error(f"{item['FULLNAME']} not found in the database: {_ex}")

            if request.GET.get('update') == '4':
                # change_password()
                result = send_email_notification.delay()
                # birthday_telegram()

                pass
                #vacation_check()
                # for report_record in ReportCard.objects.filter(Q(report_card_day__gte=datetime.datetime(2023, 1, 1, 0, 0)) & Q(record_type__in=['2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', ])):
                #     report_record.delete()
                # date_admission, vacation = get_json_vacation(self.request.user.ref_key)
                # days = 0
                # for item in vacation['value']:
                #     if item['Active'] and not item['Компенсация']:
                #         if item['ВидЕжегодногоОтпуска_Key'] == 'ebbd9c67-cfaf-11e6-bad8-902b345cadc2':
                #             if datetime.datetime.strptime(item['ДатаНачала'][:10], "%Y-%m-%d") > date_admission:
                #                 days += int(item['Количество'])
                # year = relativedelta(datetime.datetime.today(), date_admission).years
                # month = relativedelta(datetime.datetime.today(), date_admission).months
                # dates = [dt for dt in rrule.rrule(rrule.MONTHLY, dtstart=date_admission, until=datetime.datetime.today())]
                # print(((len(dates)-1)*(28/12)) - days)
                # object_item = ApprovalOficialMemoProcess.objects.filter(document__official_memo_type='1')
                # for item in object_item:
                #     item.save()
                pass
                # report_card_separator_loc()
                # happy_birthday_loc()
                # Получение видов рабочего времени с 1с
                # dt = get_types_userworktime()
                # for item in dt['value']:
                #     # print(value)
                #     kwargs_obj = {
                #         'ref_key': item['Ref_Key'],
                #         'description': item['Description'],
                #         'letter_code': item['БуквенныйКод'],
                #         'active': False,
                #     }
                #     TypesUserworktime.objects.update_or_create(ref_key=item['Ref_Key'], defaults=kwargs_obj)
            if request.GET.get('update') == '5':
                # Получение неявок на рабочее место.
                get_sick_leave.delay(2025, 1)
                # report_card_separator_daily(year=2023, month=10, day=30)
                # vacation_schedule()
                pass
                # type_of_report = {
                #     '2': 'Ежегодный',
                #     '3': 'Дополнительный ежегодный отпуск',
                #     '4': 'Отпуск за свой счет',
                #     '5': 'Дополнительный учебный отпуск (оплачиваемый)',
                #     '6': 'Отпуск по уходу за ребенком',
                #     '7': 'Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС',
                #     '8': 'Отпуск по беременности и родам',
                #     '9': 'Отпуск без оплаты согласно ТК РФ',
                #     '10': 'Дополнительный отпуск',
                #     '11': 'Дополнительный оплачиваемый отпуск пострадавшим в ',
                #     '12': 'Основной',
                # }
                # all_records = 0
                # exclude_list = ['proxmox', 'shakirov']
                # for rec_item in DataBaseUser.objects.all().exclude(username__in=exclude_list).values('ref_key'):
                #     print(rec_item['ref_key'])
                #     dt = get_jsons_data_filter2('InformationRegister', 'ДанныеОтпусковКарточкиСотрудника',
                #                                 'Сотрудник_Key',
                #                                 rec_item['ref_key'], 'year(ДатаОкончания)', 2023, 0, 0)
                #     for key in dt:
                #         for item in dt[key]:
                #             for report_record in ReportCard.objects.filter(doc_ref_key=item['ДокументОснование']):
                #                 report_record.delete()
                #             usr_obj = DataBaseUser.objects.get(ref_key=item['Сотрудник_Key'])
                #             start_date = datetime.datetime.strptime(item['ДатаНачала'][:10], "%Y-%m-%d")
                #             end_date = datetime.datetime.strptime(item['ДатаОкончания'][:10], "%Y-%m-%d")
                #             weekend_count = WeekendDay.objects.filter(
                #                 Q(weekend_day__gte=start_date) & Q(weekend_day__lte=end_date) & Q(
                #                     weekend_type='1')).count()
                #             count_date = int(item['КоличествоДней']) + weekend_count
                #             period = list(rrule.rrule(rrule.DAILY, count=count_date, dtstart=start_date))
                #             weekend = [item.weekend_day for item in WeekendDay.objects.filter(
                #                 Q(weekend_day__gte=start_date.date()) & Q(weekend_day__lte=end_date.date()))]
                #             for unit in period:
                #                 if unit.weekday() in [0, 1, 2, 3] and unit.date() not in weekend:
                #                     delta_time = datetime.timedelta(
                #                         hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                #                         minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute)
                #                     start_time = usr_obj.user_work_profile.personal_work_schedule_start
                #                     end_time = datetime.datetime.strptime(str(delta_time), '%H:%M:%S').time()
                #                 elif unit.weekday() == 4 and unit not in weekend:
                #                     delta_time = datetime.timedelta(
                #                         hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                #                         minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute) - \
                #                                  datetime.timedelta(hours=1)
                #                     start_time = usr_obj.user_work_profile.personal_work_schedule_start
                #                     end_time = datetime.datetime.strptime(str(delta_time), '%H:%M:%S').time()
                #                 else:
                #                     start_time = datetime.datetime.strptime('00:00:00', '%H:%M:%S').time()
                #                     end_time = datetime.datetime.strptime('00:00:00', '%H:%M:%S').time()
                #
                #                 value = [i for i in type_of_report if
                #                          type_of_report[i] == item['ВидОтпускаПредставление']]
                #                 kwargs_obj = {
                #                     'report_card_day': unit,
                #                     'employee': usr_obj,
                #                     'start_time': start_time,
                #                     'end_time': end_time,
                #                     'reason_adjustment': item['Основание'],
                #                     'doc_ref_key': item['ДокументОснование'],
                #                 }
                #                 rec_obj, counter = ReportCard.objects.update_or_create(report_card_day=unit,
                #                                                                        employee=usr_obj,
                #                                                                        record_type=value[0],
                #                                                                        defaults=kwargs_obj)
                #                 if counter:
                #                     all_records += 1
            if request.GET.get('update') == '7':
                # Получение неявок на рабочее место.
                get_sick_leave.delay(2025, 2)
            if request.GET.get('update') == '8':
                # Получение неявок на рабочее место - Отгул
                get_sick_leave.delay(2025, 3)
            if request.GET.get('update') == '6':
                birthday_telegram.delay()
            if request.GET.get('update') == '9':
                qs = Contract.objects.all()
                for item in qs:
                    try:
                        if item.pk == item.parent_category.pk:
                            item.parent_category = None
                            item.save()
                    except AttributeError:
                        pass
            if request.GET.get('update') == '10':
                get_vacation.delay()
            if request.GET.get('update') == '11':
                get_year_report.delay()
            if request.GET.get('update') == '12':
                try:
                    groups = Groups.objects.all()
                    groups_dict = dict()
                    for item in groups:
                        jobs = Job.objects.filter(group=item)
                        users_list = []
                        for unit in jobs:
                            users_list += [user.title for user in DataBaseUser.objects.filter(user_work_profile__job=unit).exclude(is_active=False)]

                        groups_dict[item.name] = users_list
                    logger.info(f"Права групп: {groups_dict} ")
                    with open('groups.json', 'w') as f:
                        json.dump(groups_dict, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    logger.error(f"Ошибка при получении прав групп: {e}")
            if request.GET.get('update') == '13':
                save_report.delay()
            if request.GET.get('update') == '14':
                vacation_schedule_send.delay()
                # vacation_schedule_send()
            if request.GET.get('update') == '15':
                vacation_check.delay()
            if request.GET.get('update') == '16':
                export_users_to_csv('users_export.csv')

        return super().get(request, *args, **kwargs)

@login_required
def system_monitor(request):
    return render(request, 'administration_app/system_monitor.html')