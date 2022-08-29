import pathlib

from django.shortcuts import redirect
from django.urls import reverse_lazy
from docxtpl import DocxTemplate
from docx2pdf import convert

from contracts_app.models import TypeContract, TypeProperty, Contract
from customers_app.models import DataBaseUser, Counteragent, Division, UserAccessMode
from djangoProject.settings import BASE_DIR


class GetAllObject:

    def get_object(self):
        context = {}
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context


def transliterate(name):
    """
    Функция транслитерации строки, с русского в английский
    :param name: Заданная строка
    :return: Результат транслитерации
    """
    slovar = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
              'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
              'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h',
              'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e',
              'ю': 'u', 'я': 'ya', 'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'YO',
              'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'I', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
              'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H',
              'Ц': 'C', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH', 'Ъ': '', 'Ы': 'y', 'Ь': '', 'Э': 'E',
              'Ю': 'U', 'Я': 'YA', ',': '', '?': '', ' ': '_', '~': '', '!': '', '@': '', '#': '',
              '$': '', '%': '', '^': '', '&': '', '*': '', '(': '', ')': '', '-': '', '=': '', '+': '',
              ':': '', ';': '', '<': '', '>': '', '\'': '', '"': '', '\\': '', '/': '', '№': '',
              '[': '', ']': '', '{': '', '}': '', 'ґ': '', 'ї': '', 'є': '', 'Ґ': 'g', 'Ї': 'i',
              'Є': 'e', '—': ''}

    # Циклически заменяем все буквы в строке
    for key in slovar:
        name = name.replace(key, slovar[key])
    return name


def ChangeAccess(obj):
    # for key, value in kwargs:
    #     obj[key] = True
    print(9)


def Med(obj_model, filepath, filename):
    doc = DocxTemplate(pathlib.Path.joinpath(BASE_DIR, 'static/DocxTemplates/med.docx'))
    print(obj_model.person.user_work_profile.job.pk)
    if obj_model.person.gender == 'male':
        gender = 'муж.'
    else:
        gender = 'жен.'
    try:
        context = {'gender': gender,
                   'birthday': obj_model.person.birthday.strftime("%d.%m.%Y"),
                   'division': obj_model.person.user_work_profile.divisions,
                   'job': obj_model.person.user_work_profile.job,
                   'FIO': obj_model.person,
                   'snils': obj_model.person.user_profile.snils,
                   'oms': obj_model.person.user_profile.oms,
                   'status': obj_model.get_working_status_display(),
                   'harmful_name': obj_model.harmful.name,
                   'harmful_code': obj_model.harmful.code,
                   'organisation': obj_model.organisation,
                   'ogrn': obj_model.organisation.ogrn,
                   'email': obj_model.organisation.email,
                   'tel': obj_model.organisation.phone,
                   'address': obj_model.organisation.juridical_address,
                   }
    except Exception as _ex:
        context = {}
    doc.render(context)
    path_obj = pathlib.Path.joinpath(pathlib.Path.joinpath(BASE_DIR, filepath))
    if not path_obj.exists():
        path_obj.mkdir(parents=True)
    doc.save(pathlib.Path.joinpath(path_obj, filename))
    #ToDo: Попытка конвертации docx в pdf в Linux. Не работает
    # convert(filename, (filename[:-4]+'pdf'))
    # convert(filepath)


def boolean_return(request, check_string):
    is_checked = request.POST.get(check_string, False)
    if is_checked == 'on':
        return True
    return False