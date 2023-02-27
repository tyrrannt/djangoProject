import datetime

from administration_app.utils import get_jsons_data_filter, get_jsons
from customers_app.models import DataBaseUser, Job, Division, DataBaseUserWorkProfile


def get_database_user_profile(ref_key):
    """
    Получение полиса ОМС из Регистра сведений
    :return: Найденную запись, или пустую строку
    """
    context = ""
    item = get_jsons_data_filter("InformationRegister", "ПолисыОМСФизическихЛиц", "ФизическоеЛицо_Key", ref_key, 0, 0)
    for record in item['value']:
        context = record['НомерПолиса']
    return context


def get_database_user_work_profile():
    """
    Получение подразделения, должности и даты приема на работу сотрудника,
    :return: Найденную запись, или пустую строку
    """
    context = ""
    users_list = DataBaseUser.objects.all().exclude(is_superuser=True)
    for units in users_list:
        job_code, division_code, date_of_employment = '', '', '1900-01-01'
        todo_str = get_jsons(
            f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_КадроваяИсторияСотрудников?$format=application/json;odata=nometadata&$filter=RecordSet/any(d:%20d/Сотрудник_Key%20eq%20guid%27{units.ref_key}%27)")
        period = datetime.datetime.strptime("1900-01-01", "%Y-%m-%d")
        if units.ref_key != "":
            moving = 0
            for items in todo_str['value']:
                for items2 in items['RecordSet']:
                    if items2['Active'] == True and items2['ВидСобытия'] == 'Перемещение':
                        if period < datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d"):
                            period = datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d")
                            division_code = items2['Подразделение_Key']
                            job_code = items2['Должность_Key']
                            moving = 1

                    if items2['Active'] == True and items2['ВидСобытия'] == 'Прием':
                        date_of_employment = datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d")
                        if moving == 0:
                            division_code = items2['Подразделение_Key']
                            job_code = items2['Должность_Key']
            user_work_profile = {
                # 'ref_key': units.ref_key,
                'date_of_employment': date_of_employment,
                'job': Job.objects.get(ref_key=job_code) if job_code not in ["",
                                                                             '00000000-0000-0000-0000-000000000000'] else None,
                'divisions': Division.objects.get(ref_key=division_code) if division_code not in ["",
                                                                                                  '00000000-0000-0000-0000-000000000000'] else None,
            }

            DataBaseUserWorkProfile.objects.update_or_create(ref_key=units.ref_key, defaults=user_work_profile)

            if not units.user_work_profile:
                units.user_work_profile = DataBaseUserWorkProfile.objects.get(ref_key=units.ref_key)
                units.save()
    return context