import datetime

from dateutil import rrule
from dateutil.relativedelta import relativedelta
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from loguru import logger

from administration_app.utils import get_jsons_data
from customers_app.models import DataBaseUser, HarmfulWorkingConditions
from djangoProject.settings import EMAIL_HOST_USER, DEBUG
from hrdepartment_app.models import MedicalOrganisation, Medical, ReportCard, PreHolidayDay, WeekendDay, check_day


def get_medical_documents():
    type_inspection = [
        ('1', 'Предварительный'),
        ('2', 'Периодический'),
        ('3', 'Внеплановый')
    ]
    todos = get_jsons_data("Document", "НаправлениеНаМедицинскийОсмотр", 0)
    db_users = DataBaseUser.objects.all()
    harmfuls = HarmfulWorkingConditions.objects.all()
    # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
    for item in todos['value']:
        if item['Posted']:
            db_user = db_users.filter(person_ref_key=item['ФизическоеЛицо_Key'])
            db_med_org = item['МедицинскаяОрганизация_Key']
            if db_user.count() > 0 and db_med_org != '00000000-0000-0000-0000-000000000000':
                qs = list()
                for items in item['ВредныеФакторыИВидыРабот']:
                    qs.append(harmfuls.get(ref_key=items['ВредныйФактор_Key']))
                try:
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'number': item['Number'],
                        'person': db_users.get(person_ref_key=item['ФизическоеЛицо_Key']),
                        'date_entry': datetime.datetime.strptime(item['Date'][:10], "%Y-%m-%d"),
                        'date_of_inspection': datetime.datetime.strptime(item['ДатаОсмотра'][:10], "%Y-%m-%d"),
                        'organisation': MedicalOrganisation.objects.get(ref_key=item['МедицинскаяОрганизация_Key']),
                        'working_status': 1 if next(
                            x[0] for x in type_inspection if x[1] == item['ТипОсмотра']) == 1 else 2,
                        'view_inspection': 1 if item['ВидОсмотра'] == 'МедицинскийОсмотр' else 2,
                        'type_inspection': next(x[0] for x in type_inspection if x[1] == item['ТипОсмотра']),
                        # 'harmful': qs,
                    }
                    db_instance, created = Medical.objects.update_or_create(ref_key=item['Ref_Key'],
                                                                            defaults=divisions_kwargs)
                    db_instance.harmful.set(qs)
                except Exception as _ex:
                    logger.error(f'Не найдена медицинская организация. Физическое лицо: {db_user}')
                    return 'Необходимо обновить список медицинских организаций.'
    return ''


def send_mail_change(counter, obj):
    mail_to = obj.person.email
    mail_to_copy_first = obj.responsible.email
    mail_to_copy_second = obj.docs.person_distributor.email
    mail_to_copy_third = obj.docs.person_department_staff.email
    subject_mail = obj.title
    current_context = {
        'title': obj.get_title(),
        'order_number': str(obj.order.document_number),
        'order_date': str(obj.order.document_date),
    }
    logger.debug(f'Email string: {current_context}')
    text_content = render_to_string('hrdepartment_app/email_change_bpmemo.html', current_context)
    html_content = render_to_string('hrdepartment_app/email_change_bpmemo.html', current_context)

    try:
        if counter == 1:
            first_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
                                               [mail_to, mail_to_copy_first])
            second_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
                                                [mail_to_copy_second, mail_to_copy_third])
            first_msg.attach_alternative(html_content, "text/html")
            second_msg.attach_alternative(html_content, "text/html")
            first_msg.send()
            second_msg.send()
        else:
            first_msg = EmailMultiAlternatives(subject_mail, text_content, EMAIL_HOST_USER,
                                               [mail_to_copy_first, mail_to_copy_second])
            first_msg.attach_alternative(html_content, "text/html")
            first_msg.send()

    except Exception as _ex:
        logger.debug(f'Failed to send email. {_ex}')


def get_month(period):
    """
    Функция get_month, принимает в качестве аргумента переменную datetime, и на основании нее определяет первый и
    последний день месяца. В качестве результата работы выдает список [[день, Я], [день, В]...]
    :param period: Любой день месяца
    :return: Список [[день, Я], [день, В]...]
    """
    first_day = period + relativedelta(day=1)
    last_day = period + relativedelta(day=31)
    weekend_days = [item.weekend_day for item in
                    WeekendDay.objects.filter(Q(weekend_day__gte=first_day) & Q(weekend_day__lte=last_day))]
    get_month_obj = []
    for item in range(first_day.day, last_day.day + 1):
        date_obj = first_day + datetime.timedelta(days=item - 1)
        current_day = datetime.date(date_obj.year, date_obj.month, date_obj.day)
        if date_obj.weekday() in [0, 1, 2, 3, 4]:
            if current_day in list(weekend_days):
                get_month_obj.append([current_day, 'В'])
            else:
                get_month_obj.append([current_day, 'Я'])
        else:
            get_month_obj.append([current_day, 'В'])
    return get_month_obj


def get_preholiday_day(item, hour, minute, user_start_time, user_end_time):
    """
    Проверка даты на предпраздничный день.
    :param curent_day: День
    :param hour: Количество часов
    :param minute: Количество минут
    :return: Если передано нулевое время, то возвращается тоже нулевое. Если передано не нулевое время, а день оказался
    предпраздничным, то возвращается время заданное в предпраздничном дне, иначе возвращается, то время, которое пришло.
    Также возвращается врорым аргументом время окончания рабочего времени
    """
    check = 0
    curent_day = item.report_card_day
    if item.record_type == '1':
        check = 0
    if item.record_type in ['2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']:
        check = 1
    start_time = datetime.timedelta(hours=user_start_time.hour, minutes=user_start_time.minute)
    new_start_time = datetime.timedelta(hours=0, minutes=0)
    # Проверка на выходной. Если истина, то вернуть нулевое время
    holiday_day = WeekendDay.objects.filter(weekend_day=curent_day).exists()
    if check == 1:
        end_time = datetime.timedelta(hours=0, minutes=0)
        new_start_time = datetime.timedelta(hours=0, minutes=0)
        if curent_day.weekday() in [0, 1, 2, 3]:
            return datetime.timedelta(hours=8, minutes=30), new_start_time, end_time
        elif curent_day.weekday() == 4:
            return datetime.timedelta(hours=7, minutes=30), new_start_time, end_time
        else:
            return datetime.timedelta(hours=0, minutes=0), new_start_time, end_time
    if holiday_day:
        end_time = start_time + datetime.timedelta(hours=0, minutes=0)
        return datetime.timedelta(hours=0, minutes=0), new_start_time, end_time
    try:
        pre_holiday_day = PreHolidayDay.objects.get(preholiday_day=curent_day)
        if hour == 0 and minute == 0:
            end_time = start_time + datetime.timedelta(hours=hour, minutes=minute)
            return datetime.timedelta(hours=hour, minutes=minute), new_start_time, end_time
        else:
            end_time = start_time + datetime.timedelta(hours=pre_holiday_day.work_time.hour,
                                                       minutes=pre_holiday_day.work_time.minute)
            return datetime.timedelta(hours=pre_holiday_day.work_time.hour,
                                      minutes=pre_holiday_day.work_time.minute), new_start_time, end_time

    except Exception as _ex:
        end_time = start_time + datetime.timedelta(hours=hour, minutes=minute)
        return datetime.timedelta(hours=hour, minutes=minute), new_start_time, end_time


def get_report_card(pk, RY=None, RM=None):
    """

    :param pk: УИН пользователя
    :param RY: Год
    :param RM: Месяц
    :return:
    """
    # Устанавливаем период, и получаем первый и последний день месяца
    if RY and RM:
        try:
            sample_date = datetime.datetime(int(RY), int(RM), 1)
        except TypeError:
            sample_date = datetime.datetime(2023, 1, 1)
        first_day = sample_date + relativedelta(day=1)
        last_day = sample_date + relativedelta(day=31)
    # Иначе устанавливаем в качестве периода текущий месяц
    else:
        first_day = datetime.datetime.today() + relativedelta(day=1)
        last_day = datetime.datetime.today() + relativedelta(day=31)

    total_score = 0
    get_user = DataBaseUser.objects.get(pk=pk)
    user_start_time = get_user.user_work_profile.personal_work_schedule_start
    user_end_time = get_user.user_work_profile.personal_work_schedule_end

    print(get_working_hours(get_user, first_day))

    data_dict = dict()
    for item in ReportCard.objects.filter(
            Q(report_card_day__gte=first_day) & Q(report_card_day__lte=last_day) & Q(employee=get_user)).order_by(
        'report_card_day'):
        # Если выходной словарь еще не заполнялся, то создаем пустой элемент с ключем (УИН пользователя)
        if not data_dict.get(str(item.employee)):
            data_dict[str(item.employee)] = []
        # Получаем время прихода
        time_1 = datetime.timedelta(hours=item.start_time.hour, minutes=item.start_time.minute)
        # Получаем время ухода
        time_2 = datetime.timedelta(hours=item.end_time.hour, minutes=item.end_time.minute)
        if item.report_card_day.weekday() in [0, 1, 2, 3]:
            time_3, new_start_time, end_time = get_preholiday_day(item, 8, 30, user_start_time, user_end_time)
        elif item.report_card_day.weekday() == 4:
            time_3, new_start_time, end_time = get_preholiday_day(item, 7, 30, user_start_time, user_end_time)
        else:
            time_3, new_start_time, end_time = get_preholiday_day(item, 0, 0, user_start_time, user_end_time)
        if time_2.total_seconds() - time_1.total_seconds() == 60.0:
            time_4 = time_2.total_seconds() - time_1.total_seconds()
        else:
            time_4 = (time_2.total_seconds() - time_1.total_seconds()) - time_3.total_seconds()
        total_score += time_4
        sign = '-' if time_4 < 0 else ''
        time_delta = datetime.timedelta(seconds=abs(time_4))
        data_dict[str(item.employee)].append(
            [item.report_card_day, item.start_time, item.end_time, sign, time_delta, end_time])
    return data_dict, total_score, first_day, last_day, user_start_time, user_end_time


# -------------------------------------------------------------------------------------------------------------------

def get_working_hours(pk, start_date, state=0):
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
    user_id = DataBaseUser.objects.get(pk=pk)
    cnt = start_date + relativedelta(day=31)
    period = list(rrule.rrule(rrule.DAILY, count=cnt.day, dtstart=start_date.date()))
    dict_obj = dict()
    total_time = 0
    all_total_time = 0
    all_days_count = 0
    all_vacation_days = 0
    all_vacation_time = 0
    holiday_delta = 0
    for date in period:
        if not dict_obj.get(str(user_id)):
            dict_obj[str(user_id)] = []
        report_record = ReportCard.objects.filter(employee=user_id, report_card_day=date).order_by(
            'record_type').reverse()
        total_day_time, start_time, end_time, record_type, sign, merge_interval, time_worked = 0, '', '', '', '', '', 0
        user_start_time = user_id.user_work_profile.personal_work_schedule_start
        user_end_time = user_id.user_work_profile.personal_work_schedule_end
        current_intervals = True

        for record in report_record:
            # Выбираем только завершенные записи, если человек не отметился на выход, то current_intervals = False
            current_intervals = False if not current_intervals else record.current_intervals
            if (record.record_type == '1' or record.record_type == '13') and record_type not in ['СП', 'К', 'Б', ]:
                if current_intervals:
                    total_day_time += datetime.timedelta(
                        hours=record.end_time.hour, minutes=record.end_time.minute).total_seconds() \
                                      - datetime.timedelta(hours=record.start_time.hour,
                                                           minutes=record.start_time.minute).total_seconds()
                if start_time == '':
                    start_time = record.start_time
                else:
                    if start_time == datetime.datetime(1, 1, 1, 0, 0).time():
                        start_time = record.start_time
                    if record.start_time < start_time and record.start_time != datetime.datetime(1, 1, 1, 0, 0).time():
                        start_time = record.start_time
                if end_time == '':
                    end_time = record.end_time
                else:
                    if record.end_time > end_time:
                        end_time = record.end_time
                if record_type not in ['О', 'СП', 'К']:
                    record_type = 'Я'
            else:
                if record.record_type == '14' or record.record_type == '15':
                    total_day_time = datetime.timedelta(
                        hours=record.end_time.hour, minutes=record.end_time.minute).total_seconds() \
                                      - datetime.timedelta(hours=record.start_time.hour,
                                                           minutes=record.start_time.minute).total_seconds()
                    start_time = record.start_time
                    end_time = record.end_time
                    if record.record_type == '14' and record_type != 'О':
                        record_type = 'СП'
                    if record.record_type == '15' and record_type != 'О':
                        record_type = 'К'
                elif record.record_type == '16':
                    pass
                else:
                    start_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    end_time = datetime.datetime(1, 1, 1, 0, 0).time()
                    total_day_time += 0
                    record_type = 'О'

        if record_type != '':
            if report_record.count() == 1:
                merge_interval = False
            else:
                merge_interval = True
            user_start_time, user_end_time = check_day(date, user_start_time, user_end_time)
            # Если только явка или ручной ввод
            if record_type == 'Я':
                all_days_count += 1
                if current_intervals:
                    time_worked = total_day_time
                    # От отработанного времени отнимаем рабочее, чтоб получить дельту
                    total_day_time -= datetime.timedelta(
                        hours=user_end_time.hour, minutes=user_end_time.minute).total_seconds() - \
                                      datetime.timedelta(
                                          hours=user_start_time.hour, minutes=user_start_time.minute).total_seconds()
            if record_type == 'СП' or record_type == 'К':
                all_days_count += 1
                time_worked = total_day_time
                # От отработанного времени отнимаем рабочее, чтоб получить дельту
                total_day_time -= datetime.timedelta(
                    hours=user_end_time.hour, minutes=user_end_time.minute).total_seconds() - \
                                  datetime.timedelta(
                                      hours=user_start_time.hour, minutes=user_start_time.minute).total_seconds()
            # Если только отпуск
            if record_type == 'О' and report_record.count() == 1:
                total_time += 0
                all_total_time += 0
                if user_end_time.hour > 0:
                    all_vacation_days += 1
                all_vacation_time += datetime.timedelta(hours=user_end_time.hour, minutes=user_end_time.minute).total_seconds() - datetime.timedelta(hours=user_start_time.hour, minutes=user_start_time.minute).total_seconds()
            if record_type == 'Я':
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour == 0:
                    holiday_delta += 1
            if record_type == 'СП' or record_type == 'К':
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour == 0:
                    holiday_delta += 1
            if record_type == 'О' and merge_interval:
                time_worked = total_day_time
                total_time += total_day_time
                all_total_time += time_worked
                if user_end_time.hour > 0:
                    all_vacation_days += 1
                all_vacation_time += datetime.timedelta(hours=user_end_time.hour,
                                                        minutes=user_end_time.minute).total_seconds() - datetime.timedelta(
                    hours=user_start_time.hour, minutes=user_start_time.minute).total_seconds()
            sign = ''
            if total_day_time < 0:
                sign = '-'
            """ Дата, Начало, Окончание, Знак, Скалярное общее время за день, Начало по графику, 
            Окончание по графику, Тип записи, Было ли объединение интервалов,
             Начальная дата, Общее за день"""

        start_time = start_time if start_time != '' else datetime.datetime(1, 1, 1, 0, 0).time()
        end_time = end_time if end_time != '' else datetime.datetime(1, 1, 1, 0, 0).time()
        if state == 0:
            dict_obj[str(user_id)].append(
                [date.date(), start_time, end_time, sign, abs(total_day_time), user_start_time,
                 user_end_time, record_type, merge_interval, current_intervals, time_worked])
        else:
            time_worker = datetime.datetime(1, 1, 1, 0, 0).time().strftime('%H:%M') if time_worked == 0 else datetime.datetime.strptime(str(datetime.timedelta(seconds=time_worked)), '%H:%M:%S').time().strftime('%H:%M')
            dict_obj[str(user_id)].append(
                [date.date(), record_type, time_worker])
    if state == 0:
        return dict_obj, total_time, start_date, cnt
    else:
        result = dict_obj[str(user_id)]
        return result, all_total_time, all_days_count, all_vacation_days, all_vacation_time, holiday_delta
