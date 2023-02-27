import datetime

from loguru import logger

from administration_app.utils import get_jsons_data_filter, get_jsons, get_jsons_data, transliterate
from customers_app.models import DataBaseUser, Job, Division, DataBaseUserWorkProfile, DataBaseUserProfile


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


def get_database_user():
    count = DataBaseUser.objects.all().count() + 1
    staff = get_jsons_data("Catalog", "Сотрудники", 0)
    individuals = get_jsons_data("Catalog", "ФизическиеЛица", 0)
    insurance_policy = get_jsons_data("InformationRegister", "ПолисыОМСФизическихЛиц", 0)
    # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
    for item in staff['value']:
        if item['Description'] != "" and item['ВАрхиве'] == False:
            Ref_Key, username, first_name = '', '', ''
            personal_kwargs = {}
            last_name, surname, birthday, gender, email, telephone, address, = '', '', '1900-01-01', '', '', '', '',
            individuals_item = [items for items in individuals['value'] if items['Ref_Key'] == item['ФизическоеЛицо_Key']]
            for item2 in individuals_item:
                Ref_Key = item2['Ref_Key']
                username = '0' * (4 - len(str(count))) + str(count) + '_' + transliterate(
                    item2['Фамилия']).lower() + '_' + \
                           transliterate(item2['Имя']).lower()[:1] + \
                           transliterate(item2['Отчество']).lower()[:1]
                first_name = item2['Имя']
                last_name = item2['Фамилия']
                surname = item2['Отчество']
                gender = 'male' if item2['Пол'] == 'Мужской' else 'female'
                birthday = datetime.datetime.strptime(item2['ДатаРождения'][:10], "%Y-%m-%d")
                for item3 in item2['КонтактнаяИнформация']:
                    if item3['Тип'] == 'АдресЭлектроннойПочты':
                        email = item3['АдресЭП']
                    if item3['Тип'] == 'Телефон':
                        telephone = '+' + item3['НомерТелефона']
                    if item3['Тип'] == 'Адрес':
                        address = item3['Представление']
                oms = ''
                insurance_policy_item = [items for items in insurance_policy['value'] if items['ФизическоеЛицо_Key'] == item['ФизическоеЛицо_Key']]
                for insurance_item in insurance_policy_item:
                    oms = insurance_item['НомерПолиса']
                personal_kwargs = {
                    'inn': item2['ИНН'],
                    'snils': item2['СтраховойНомерПФР'],
                    'oms': oms,
                }

            divisions_kwargs = {
                # 'ref_key': item['Ref_Key'],
                'person_ref_key': Ref_Key,
                'service_number': item['Code'],
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'surname': surname,
                'birthday': birthday,
                'type_users': 'staff_member',
                'gender': gender,
                'email': email,
                'personal_phone': telephone[:12],
                'address': address,
            }
            count += 1
            try:
                main_obj_item, main_created = DataBaseUser.objects.update_or_create(ref_key=item['Ref_Key'],
                                                                                    defaults={**divisions_kwargs})
            except Exception as _ex:
                logger.error(f'Сохранение пользователя: {username}, {last_name} {first_name} {_ex}')
            try:
                obj_item, created = DataBaseUserProfile.objects.update_or_create(ref_key=item['Ref_Key'],
                                                                         defaults={**personal_kwargs})
            except Exception as _ex:
                logger.error(f'Сохранение профиля пользователя: {_ex}')
            if not main_obj_item.user_profile:
                try:
                    main_obj_item.user_profile = DataBaseUserProfile.objects.get(ref_key=main_obj_item.ref_key)
                    main_obj_item.save()
                except Exception as _ex:
                    logger.error(f'Сохранения профиля пользователя в модели пользователя: {_ex}')
