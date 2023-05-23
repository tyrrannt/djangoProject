import datetime

from loguru import logger

from administration_app.utils import get_jsons_data_filter, get_jsons, get_jsons_data, transliterate
from customers_app.models import DataBaseUser, Job, Division, DataBaseUserWorkProfile, DataBaseUserProfile, \
    IdentityDocuments


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
            f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_КадроваяИсторияСотрудников?$format=application/json;odata=nometadata&$filter=RecordSet/any(d:%20d/Сотрудник_Key%20eq%20guid%27{units.ref_key}%27)", 0)
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
            individuals_item = [items for items in individuals['value'] if
                                items['Ref_Key'] == item['ФизическоеЛицо_Key']]
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
                insurance_policy_item = [items for items in insurance_policy['value'] if
                                         items['ФизическоеЛицо_Key'] == item['ФизическоеЛицо_Key']]
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
                if main_created:
                    main_obj_item.username = username
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


def get_identity_documents():
    """
        Получение паспортных данных сотрудника,
        :return: Найденную запись, или пустую строку
        """
    context = ""
    users_list = DataBaseUser.objects.all().exclude(is_superuser=True)
    for units in users_list:
        ref_key, series, number, issued_by_whom, date_of_issue, division_code = '', '', '', '', '1900-01-01', ''
        todo_str = get_jsons(
            f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_ДокументыФизическихЛиц?$format=application/json;odata=nometadata&$filter=Физлицо_Key%20eq%20guid%27{units.person_ref_key}%27", 0)
        period = datetime.datetime.strptime("1900-01-01", "%Y-%m-%d")
        if units.person_ref_key != "":
            user_identity_documents = {}
            for items in todo_str['value']:
                if items['ВидДокумента_Key'] == 'ebbd9c1f-cfaf-11e6-bad8-902b345cadc2':
                    if period < datetime.datetime.strptime(items['ДатаВыдачи'][:10], "%Y-%m-%d"):
                        period = datetime.datetime.strptime(items['ДатаВыдачи'][:10], "%Y-%m-%d")
                        ref_key = units.person_ref_key
                        series = items['Серия']
                        number = items['Номер']
                        issued_by_whom = items['КемВыдан']
                        date_of_issue = datetime.datetime.strptime(items['ДатаВыдачи'][:10], "%Y-%m-%d")
                        division_code = items['КодПодразделения']

            user_identity_documents = {
                'series': series,
                'number': number,
                'issued_by_whom': issued_by_whom,
                'date_of_issue': date_of_issue,
                'division_code': division_code,
            }
            main_obj_item, main_created = IdentityDocuments.objects.update_or_create(ref_key=units.person_ref_key,
                                                                                     defaults=user_identity_documents)
            if main_created:
                obj_item = DataBaseUserProfile.objects.get(ref_key=units.ref_key)
                obj_item.passport = main_obj_item
                obj_item.save()
    return context


def get_chart_of_calculation_types(select_uuid):
    todo_str = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/ChartOfCalculationTypes_Начисления?$format=application/json;odata=nometadata&$filter=Ref_Key%20eq%20guid%27{select_uuid}%27&$select=Description", 0)
    result = ''
    try:
        for item in todo_str['value']:
            result = item['Description']
    except Exception as _ex:
        pass
    return result


def get_worked_out_by_the_workers(selected_month, selected_year, users_uuid, calculation_uud) -> list:
    acc_reg_time = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ОтработанноеВремяПоСотрудникам_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27%20and%20Начисление_Key%20eq%20guid%27{calculation_uud}%27", 0)
    days_worked, hours_worked, paid_days = '', '', ''
    try:
        for item in acc_reg_time['value']:
            days_worked = item['ОтработаноДней']
            hours_worked = item['ОтработаноЧасов']
            paid_days = item['ОплаченоДней']
    except Exception as _ex:
        pass
    result = [days_worked, hours_worked, paid_days]
    return result


def get_report_card_table(data_dict, total_score, first_day, last_day):
    """

    :param data_dict:
    :param total_score:
    :param first_day: Первый день запрашиваемого периода
    :param last_day: Последний день запрашиваемого периода
    :return:
    """
    html_obj = f"""<table class="table table-ecommerce-simple table-striped mb-0" id="datatable-ecommerce-list"
                                   style="min-width: 380px; display: block; height: 700px; overflow: auto;">
                        <tbody>
                            <tr>
                                <td colspan="4"><h4>Выполнение графика:</h4></td>
                            </tr>
                            <tr>
                                <td colspan="4">За период с: {first_day.strftime('%d-%m-%Y')} по: {last_day.strftime('%d-%m-%Y')}</td>
                            </tr>"""
    for key in data_dict:
        html_obj += f"""                        
                        <tr>
                            <th>Дата</th>
                            <th>Нормы</th>
                            <th>Табель</th>
                            <th>Факт</th>
                        </tr>"""
        for r1, r2, r3, r4, r5, r6 in data_dict[key]:
            end_work_time = datetime.datetime.strptime(str(r6), '%H:%M:%S').time().strftime('%H:%M')
            start_time = datetime.datetime.strptime(str(r2), '%H:%M:%S').time().strftime('%H:%M')
            end_time = datetime.datetime.strptime(str(r3), '%H:%M:%S').time().strftime('%H:%M')
            delta = datetime.datetime.strptime(str(r5), '%H:%M:%S').time().strftime('%H:%M')
            html_obj += f"""<tr>
                                <td>{r1.strftime('%d-%m-%Y')}</td>
                                <td><span style="{' color: #ff0000;' if r4 == '-' else ''}">{r4}{delta}</span>
                                </td>
                                <td>9:30-{end_work_time}</td>"""
            if datetime.timedelta(hours=r3.hour, minutes=r3.minute).total_seconds()-datetime.timedelta(hours=r2.hour, minutes=r2.minute).total_seconds() == 60.0:
                html_obj += f"""<td>На работе</td>
                            </tr>"""
            else:
                html_obj += f"""
                                <td>{start_time}-{end_time}</td>
                            </tr>"""
        html_obj += f"""
                         <tr>
                            <th>Итого:</th>
                            <th><span style="{' color: #ff0000;' if total_score < 0 else ''}">{'-' if total_score < 0 else ''}{datetime.datetime.strptime(str(datetime.timedelta(seconds=abs(total_score))), '%H:%M:%S').time().strftime('%H:%M')}</span></th>
                            <th></th>
                            <th></th>
                            </tr>"""

    html_obj += f"""
        </tbody>
    </table>     
    """
    return html_obj


def get_settlement_sheet(selected_month, selected_year, users_uuid):
    """
            Получение расчетного листка сотрудника,
            :return: Найденную запись, или пустую строку
            """
    ref_key, series, number, issued_by_whom, date_of_issue, division_code = '', '', '', '', '1900-01-01', ''
    acc_reg_acc = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_НачисленияУдержанияПоСотрудникам_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27", 0)
    # Поля Active = True, ФизическоеЛицо_Key = uuid, Начисление_Key = uuid, ОтработаноДней, ОтработаноЧасов, ОплаченоДней, ОплаченоЧасов, ГруппаНачисленияУдержанияВыплаты = Выплачено
    acc_reg_set = get_jsons(
        f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/AccumulationRegister_ВзаиморасчетыССотрудниками_RecordType?$format=application/json;odata=nometadata&$filter=ФизическоеЛицо_Key%20eq%20guid%27{users_uuid}%27%20and%20Period%20eq%20datetime%27{selected_year}-{selected_month}-01T00:00:00%27%20and%20ГруппаНачисленияУдержанияВыплаты%20eq%20%27Выплачено%27", 0)
    # Поля Active = True, ФизическоеЛицо_Key = uuid, СтатьяРасходов_Key = uuid, СуммаВзаиморасчетов, ГруппаНачисленияУдержанияВыплаты = Выплачено, Recorder = uuid, Recorder_Type = Document_ВедомостьНаВыплатуЗарплатыВКассу или Document_ВедомостьНаВыплатуЗарплатыВБанк
    # f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/{Recorder_Type}?$format=application/json;odata=nometadata&$filter=Состав/any(d:%20d/Ref_Key%20eq%20guid%27{Recorder}%27)&$select=Number,%20Date"
    period = datetime.datetime.strptime(f"{selected_year}-{selected_month}-01", "%Y-%m-%d")
    data_positive = list()
    data_negative = list()
    data_paid = list()
    positive = 0
    negative = 0
    paid = 0
    result_positive, result_negative, result_paid = {}, {}, {}
    for items in acc_reg_acc['value']:
        if period == datetime.datetime.strptime(items['Period'][:10], "%Y-%m-%d") and items['Active'] == True:
            work_time = get_worked_out_by_the_workers(selected_month, selected_year, users_uuid,
                                                      items['НачислениеУдержание'])
            if items['ГруппаНачисленияУдержанияВыплаты'] == 'Начислено':
                result_positive = {
                    'description': get_chart_of_calculation_types(items['НачислениеУдержание']),
                    'days_worked': work_time[0] if work_time[0] != 0 else '',
                    'hours_worked': work_time[1] if work_time[1] != 0 else '',
                    'paid_days': work_time[2] if work_time[2] != 0 else '',
                    'summ': "{:.2f}".format(items['Сумма']),
                }
                data_positive.append(result_positive)
            else:
                result_negative = {
                    'description': items['НачислениеУдержание'],
                    'summ': "{:.2f}".format(items['Сумма']),
                }
                data_negative.append(result_negative)
            if items['ГруппаНачисленияУдержанияВыплаты'] == 'Начислено':
                try:
                    positive += float(items['Сумма'])
                except Exception as _ex:
                    pass
            else:
                try:
                    negative += float(items['Сумма'])
                except Exception as _ex:
                    pass
    for items in acc_reg_set['value']:
        result_paid = {
            'document': items['ВидВзаиморасчетов'],
            'summ': "{:.2f}".format(items['СуммаВзаиморасчетов'])
        }
        paid += float(items['СуммаВзаиморасчетов'])
        data_paid.append(result_paid)
    accrued_table_set = ''
    withheld_table_set = ''
    paid_table_set = ''
    accrued_table_set_list = ''
    for count in data_positive:
        accrued_table_set_list += '<tr>'
        for key in count:
            if key == 'summ':
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            elif key in ['days_worked', 'hours_worked', 'paid_days']:
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">{count[key]}</td>'
            else:
                accrued_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        accrued_table_set_list += '</tr>'

    withheld_table_set_list = ''
    for count in data_negative:
        withheld_table_set_list += '<tr>'
        for key in count:
            if key == 'summ':
                withheld_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            else:
                withheld_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        withheld_table_set_list += '</tr>'
    paid_table_set_list = ''
    for count in data_paid:
        paid_table_set_list += '<tr>'
        for key in count:
            if key == 'summ':
                paid_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right">{count[key]}</td>'
            else:
                paid_table_set_list += f'<td style="border: 1px; border-style: solid; border-color: #01114d">{count[key]}</td>'
        paid_table_set_list += '</tr>'
    html_obj = list()
    accrued_table_set = f'''<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a"><thead>
    <tr>
        <th rowspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
        <th colspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Рабочие</th>
        <th rowspan="2" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Оплачено</th>
        <th rowspan="2" width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
    </tr>
        <tr>
        <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Дни</th>
        <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Часы</th>
    </tr>
    </thead>
    <tbody>
    <tr><td colspan="4" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Начислено:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(positive)}</strong></span></td></tr>
    {accrued_table_set_list}
     </tbody>
     </table>'''
    withheld_table_set = f'''<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a">
    <thead>
        <tr>
            <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
            <th width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
        </tr>
    </thead>
    <tbody>
         <tr><td colspan="1" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Удержано:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(negative)}</strong></span></td></tr>
    {withheld_table_set_list}
    </tbody>
    </table>'''
    paid_table_set = f'''<table style="width: 100%; border: 1px; border-style: solid; border-color: #0a0a0a">
    <thead>
        <tr>
            <th style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Вид</th>
            <th width="15%" style="border: 1px; border-style: solid; border-color: #01114d; text-align:center">Сумма</th>
        </tr>
    </thead>
    <tbody>
         <tr><td colspan="1" style="border: 1px; border-style: solid; border-color: #01114d"><strong>Выплачено:</strong></td><td style="border: 1px; border-style: solid; border-color: #01114d; text-align:right"><span style="color:#000"><strong>{"{:.2f}".format(paid)}</strong></span></td></tr>
    {paid_table_set_list}
    </tbody>
    </table>'''
    html_obj = [accrued_table_set, withheld_table_set, paid_table_set]
    return html_obj
