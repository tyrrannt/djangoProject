import datetime

from dateutil.relativedelta import relativedelta
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from loguru import logger

from administration_app.utils import get_jsons_data
from customers_app.models import DataBaseUser, HarmfulWorkingConditions
from djangoProject.settings import EMAIL_HOST_USER, DEBUG
from hrdepartment_app.models import MedicalOrganisation, Medical, ReportCard, PreHolidayDay, WeekendDay


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
    first_day = period + relativedelta(day=1)
    last_day = period + relativedelta(day=31)
    weekend_days = WeekendDay.objects.filter(Q(weekend_day__gte=first_day) & Q(weekend_day__lte=last_day))
    get_month_obj = []
    for item in range(first_day.day, last_day.day + 1):
        date_obj = first_day + datetime.timedelta(days=item - 1)
        current_day = datetime.date(date_obj.year, date_obj.month, date_obj.day)
        if date_obj.weekday() in [0, 1, 2, 3, 4]:
            if current_day in weekend_days:
                get_month_obj.append([current_day, 'В'])
            else:
                get_month_obj.append([current_day, 'Р'])
        else:
            get_month_obj.append([current_day, 'В'])
    return get_month_obj


def get_preholiday_day(curent_day, hour, minute):
    start_time = datetime.timedelta(hours=9, minutes=30)
    try:
        pre_holiday_day = PreHolidayDay.objects.get(preholiday_day=curent_day)
        if hour == 0 and minute == 0:
            start_time += datetime.timedelta(hours=hour, minutes=minute)
            return datetime.timedelta(hours=hour, minutes=minute), start_time
        else:
            start_time += datetime.timedelta(hours=pre_holiday_day.work_time.hour,
                                             minutes=pre_holiday_day.work_time.minute)
            return datetime.timedelta(hours=pre_holiday_day.work_time.hour,
                                      minutes=pre_holiday_day.work_time.minute), start_time

    except Exception as _ex:
        start_time += datetime.timedelta(hours=hour, minutes=minute)
        return datetime.timedelta(hours=hour, minutes=minute), start_time


def get_report_card(pk, RY=None, RM=None):
    if RY and RM:
        try:
            sample_date = datetime.datetime(int(RY), int(RM), 1)
        except TypeError:
            sample_date = datetime.datetime(2023, 1, 1)
        first_day = sample_date + relativedelta(day=1)
        last_day = sample_date + relativedelta(day=31)
    else:
        first_day = datetime.datetime.today() + relativedelta(day=1)
        last_day = datetime.datetime.today() + relativedelta(day=31)
    total_score = 0
    get_user = DataBaseUser.objects.get(pk=pk)
    data_dict = dict()
    for item in ReportCard.objects.filter(
            Q(report_card_day__gte=first_day) & Q(report_card_day__lte=last_day) & Q(employee=get_user)).order_by(
        'report_card_day'):
        if not data_dict.get(str(item.employee)):
            data_dict[str(item.employee)] = []
        time_1 = datetime.timedelta(hours=item.start_time.hour, minutes=item.start_time.minute)
        time_2 = datetime.timedelta(hours=item.end_time.hour, minutes=item.end_time.minute)
        if item.report_card_day.weekday() in [0, 1, 2, 3]:
            time_3, end_time = get_preholiday_day(item.report_card_day, 8, 30)
        elif item.report_card_day.weekday() == 4:
            time_3, end_time = get_preholiday_day(item.report_card_day, 7, 30)
        else:
            time_3, end_time = get_preholiday_day(item.report_card_day, 0, 0)
        time_4 = (time_2.total_seconds() - time_1.total_seconds()) - time_3.total_seconds()
        total_score += time_4
        sign = '-' if time_4 < 0 else ''
        time_delta = datetime.timedelta(seconds=abs(time_4))
        data_dict[str(item.employee)].append(
            [item.report_card_day, item.start_time, item.end_time, sign, time_delta, end_time])
    return data_dict, total_score, first_day, last_day
