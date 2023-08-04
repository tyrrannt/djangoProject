import datetime
import json

import requests
import telebot
from dateutil import rrule
from dateutil.relativedelta import relativedelta
from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse

from django.views.generic import ListView
from loguru import logger

from administration_app.models import PortalProperty
from administration_app.utils import (
    get_users_info,
    change_users_password,
    get_jsons_data_filter,
    get_jsons_data,
    get_jsons_data_filter2,
    get_types_userworktime,
    get_date_interval,
    get_json_vacation,
)
from customers_app.models import DataBaseUser, Groups, Job, AccessLevel
from djangoProject.settings import API_TOKEN
from hrdepartment_app.models import (
    OfficialMemo,
    WeekendDay,
    ReportCard,
    TypesUserworktime,
    check_day,
    ApprovalOficialMemoProcess,
    DocumentsOrder,
)
from hrdepartment_app.tasks import (
    report_card_separator,
    report_card_separator_loc,
    happy_birthday_loc,
    change_sign,
    get_vacation,
    vacation_schedule,
)
from telegram_app.management.commands import bot
from telegram_app.management.commands.bot import send_message_tg


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


# Create your views here.


def index(request):
    pass


class PortalPropertyList(LoginRequiredMixin, ListView):
    model = PortalProperty

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context["Group"] = Groups.objects.all()
        context[
            "title"
        ] = f"{PortalProperty.objects.all().last().portal_name} // Настройки портала"
        return context

    def get(self, request, *args, **kwargs):
        if self.request.user.is_superuser:
            # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                property_list = PortalProperty.objects.all()
                data = [property_item.get_data() for property_item in property_list]
                response = {"data": data}
                return JsonResponse(response)
            # Установка общих прав пользователя наследованием из групп
            if request.GET.get("update") == "0":
                group_list = [
                    unit for unit in Groups.objects.filter(name__contains="Общая")
                ]
                job_list = Job.objects.all()
                for item in job_list:
                    for unit in group_list:
                        item.group.add(unit.id)
            # Установка прав пользователя наследованием из групп
            if request.GET.get("update") == "1":
                users_list = DataBaseUser.objects.all().exclude(
                    username="proxmox", is_active=False
                )
                for user_obj in users_list:
                    try:
                        user_obj.groups.clear()
                        for item in user_obj.user_work_profile.job.group.all():
                            user_obj.groups.add(item)
                        user_obj.save()
                    except AttributeError:
                        logger.info(f"У пользователя {user_obj} отсутствуют группы!")
                        # Установка общих прав пользователя наследованием из групп
            if request.GET.get("update") == "2":
                users_list = DataBaseUser.objects.all().exclude(is_superuser=True)
                user_access = AccessLevel.objects.get(level=3)
                for item in users_list:
                    item.user_access = user_access
                    item.save()
                # memo_list = OfficialMemo.objects.all()
                # for item in memo_list:
                #     if item.title == '':
                #         item.save()
            if request.GET.get("update") == "3":
                qs = DocumentsOrder.objects.filter(
                    Q(cancellation=False)
                    & Q(document_date__year=2023)
                    & Q(document_date__month=8)
                )
                for item in qs:
                    item.save()
                # get_vacation()
                # def get_type_of_employment(Ref_Key):
                #     data = get_jsons_data_filter("Document", "ПриемНаРаботу", 'Сотрудник_Key', Ref_Key, 0, 0, True, True)
                #     match len(data['value']):
                #         case 0:
                #             return False
                #         case 1:
                #             if data['value'][0]['ВидЗанятости'] == 'ОсновноеМестоРаботы':
                #                 return True
                #         case _:
                #             for item in data['value']:
                #                 if item['ВидЗанятости'] == 'ОсновноеМестоРаботы' and item['ИсправленныйДокумент_Key'] != "00000000-0000-0000-0000-000000000000":
                #                     return True
                #     return False
                #
                # staff = get_jsons_data_filter("Catalog", "Сотрудники", 'ВАрхиве', 'false', 0, 0, False, False)
                # individuals = get_jsons_data("Catalog", "ФизическиеЛица", 0)
                # staff_set = set()
                # for item in staff['value']:
                #     if item['Description'] != "":
                #         staff_set.add(item['Ref_Key'])
                # users_set = set()
                # for item in DataBaseUser.objects.all():
                #     users_set.add(item.ref_key)
                # users_set &= staff_set
                # print('Есть везде', len(list(users_set)))
                # staff_set -= users_set
                # staff_set_list = list()
                # for unit in list(staff_set):
                #     if get_type_of_employment(unit):
                #         staff_set_list.append(unit)
                # print('Нет в системе',  staff_set_list)
                #
                # def get_filter_list(filter_list, variable, meaning):
                #     return list(filter(lambda item_filter: item_filter[variable] == meaning, filter_list))[0]
                # for item in staff['value']:
                #     if item['Description'] != "":
                #         # find_item = list(filter(lambda item_filter: item_filter['Ref_Key'] == item['ФизическоеЛицо_Key'], individuals['value']))[0]
                #         print(get_filter_list(individuals['value'], 'Ref_Key', item['ФизическоеЛицо_Key']))
                #
                # pass
                # get_sick_leave(2023, 2)
            if request.GET.get("update") == "4":
                for report_record in ReportCard.objects.filter(
                    Q(report_card_day__gte=datetime.datetime(2023, 1, 1, 0, 0))
                    & Q(
                        record_type__in=[
                            "2",
                            "3",
                            "4",
                            "5",
                            "6",
                            "7",
                            "8",
                            "9",
                            "10",
                            "11",
                            "12",
                        ]
                    )
                ):
                    report_record.delete()
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
                # pass
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
            if request.GET.get("update") == "5":
                # pass
                type_of_report = {
                    "2": "Ежегодный",
                    "3": "Дополнительный ежегодный отпуск",
                    "4": "Отпуск за свой счет",
                    "5": "Дополнительный учебный отпуск (оплачиваемый)",
                    "6": "Отпуск по уходу за ребенком",
                    "7": "Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС",
                    "8": "Отпуск по беременности и родам",
                    "9": "Отпуск без оплаты согласно ТК РФ",
                    "10": "Дополнительный отпуск",
                    "11": "Дополнительный оплачиваемый отпуск пострадавшим в ",
                    "12": "Основной",
                }
                all_records = 0
                exclude_list = ["proxmox", "shakirov"]
                for rec_item in (
                    DataBaseUser.objects.all()
                    .exclude(username__in=exclude_list)
                    .values("ref_key")
                ):
                    print(rec_item["ref_key"])
                    dt = get_jsons_data_filter2(
                        "InformationRegister",
                        "ДанныеОтпусковКарточкиСотрудника",
                        "Сотрудник_Key",
                        rec_item["ref_key"],
                        "year(ДатаОкончания)",
                        2023,
                        0,
                        0,
                    )
                    for key in dt:
                        for item in dt[key]:
                            for report_record in ReportCard.objects.filter(
                                doc_ref_key=item["ДокументОснование"]
                            ):
                                report_record.delete()
                            usr_obj = DataBaseUser.objects.get(
                                ref_key=item["Сотрудник_Key"]
                            )
                            start_date = datetime.datetime.strptime(
                                item["ДатаНачала"][:10], "%Y-%m-%d"
                            )
                            end_date = datetime.datetime.strptime(
                                item["ДатаОкончания"][:10], "%Y-%m-%d"
                            )
                            weekend_count = WeekendDay.objects.filter(
                                Q(weekend_day__gte=start_date)
                                & Q(weekend_day__lte=end_date)
                                & Q(weekend_type="1")
                            ).count()
                            count_date = int(item["КоличествоДней"]) + weekend_count
                            period = list(
                                rrule.rrule(
                                    rrule.DAILY, count=count_date, dtstart=start_date
                                )
                            )
                            weekend = [
                                item.weekend_day
                                for item in WeekendDay.objects.filter(
                                    Q(weekend_day__gte=start_date.date())
                                    & Q(weekend_day__lte=end_date.date())
                                )
                            ]
                            for unit in period:
                                if (
                                    unit.weekday() in [0, 1, 2, 3]
                                    and unit.date() not in weekend
                                ):
                                    delta_time = datetime.timedelta(
                                        hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                                        minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute,
                                    )
                                    start_time = (
                                        usr_obj.user_work_profile.personal_work_schedule_start
                                    )
                                    end_time = datetime.datetime.strptime(
                                        str(delta_time), "%H:%M:%S"
                                    ).time()
                                elif unit.weekday() == 4 and unit not in weekend:
                                    delta_time = datetime.timedelta(
                                        hours=usr_obj.user_work_profile.personal_work_schedule_end.hour,
                                        minutes=usr_obj.user_work_profile.personal_work_schedule_end.minute,
                                    ) - datetime.timedelta(hours=1)
                                    start_time = (
                                        usr_obj.user_work_profile.personal_work_schedule_start
                                    )
                                    end_time = datetime.datetime.strptime(
                                        str(delta_time), "%H:%M:%S"
                                    ).time()
                                else:
                                    start_time = datetime.datetime.strptime(
                                        "00:00:00", "%H:%M:%S"
                                    ).time()
                                    end_time = datetime.datetime.strptime(
                                        "00:00:00", "%H:%M:%S"
                                    ).time()

                                value = [
                                    i
                                    for i in type_of_report
                                    if type_of_report[i]
                                    == item["ВидОтпускаПредставление"]
                                ]
                                kwargs_obj = {
                                    "report_card_day": unit,
                                    "employee": usr_obj,
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "reason_adjustment": item["Основание"],
                                    "doc_ref_key": item["ДокументОснование"],
                                }
                                rec_obj, counter = ReportCard.objects.update_or_create(
                                    report_card_day=unit,
                                    employee=usr_obj,
                                    record_type=value[0],
                                    defaults=kwargs_obj,
                                )
                                if counter:
                                    all_records += 1

        return super().get(request, *args, **kwargs)
