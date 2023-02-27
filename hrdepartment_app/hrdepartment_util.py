import datetime

from administration_app.utils import get_jsons_data
from customers_app.models import DataBaseUser, HarmfulWorkingConditions
from hrdepartment_app.models import MedicalOrganisation, Medical


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
                divisions_kwargs = {
                    'ref_key': item['Ref_Key'],
                    'number': item['Number'],
                    'person': db_users.get(person_ref_key=item['ФизическоеЛицо_Key']),
                    'date_entry': datetime.datetime.strptime(item['Date'][:10], "%Y-%m-%d"),
                    'date_of_inspection': datetime.datetime.strptime(item['ДатаОсмотра'][:10], "%Y-%m-%d"),
                    'organisation': MedicalOrganisation.objects.get(ref_key=item['МедицинскаяОрганизация_Key']),
                    'working_status': 1 if next(x[0] for x in type_inspection if x[1] == item['ТипОсмотра']) == 1 else 2,
                    'view_inspection': 1 if item['ВидОсмотра'] == 'МедицинскийОсмотр' else 2,
                    'type_inspection': next(x[0] for x in type_inspection if x[1] == item['ТипОсмотра']),
                    # 'harmful': qs,
                }
                db_instance, created = Medical.objects.update_or_create(ref_key=item['Ref_Key'], defaults=divisions_kwargs)
                db_instance.harmful.set(qs)
