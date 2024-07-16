import json
from pprint import pprint

from django.db.models import F, ExpressionWrapper, CharField
from django.http import HttpResponse
from django.shortcuts import render
from django.core import serializers

from administration_app.utils import get_client_ip
from customers_app.models import DataBaseUser


def json_view(request):
    dict_obj = DataBaseUser.objects.filter(is_active=False)[:3]
    queryset = serializers.serialize('json', dict_obj,
                                     fields=('last_name', 'first_name', 'surname', 'address', 'birthday', 'gender'))
    return HttpResponse(queryset, content_type='application/json')


def get_type_first(job) -> str:
    find_job = job.lower()
    if 'инженер' in find_job:
        return 'Инженер'
    elif 'техник' in find_job:
        return 'Техник'
    elif 'качеству' in find_job:
        return 'ГКК'
    else:
        return ''


def get_type_second(job) -> str:
    find_job = job.lower()
    if 'систем' in find_job:
        return 'АиРЭО'
    elif get_type_first(job) != '':
        return 'ПиД'
    else:
        return ''


def xml_view(request):
    # dict_obj = DataBaseUser.objects.filter(user_work_profile__job__type_of_job='2').values_list('service_number', 'last_name', 'first_name', 'surname', 'address', 'birthday',
    #                                      'gender', 'user_work_profile__job__name')
    # xml_obj = dict_obj
    #
    # queryset = serializers.serialize('xml', xml_obj,
    #                                  fields=(
    #                                      'service_number', 'last_name', 'first_name', 'surname', 'address', 'birthday',
    #                                      'gender', 'user_work_profile', 'job'),
    #                                  relations=('user_work_profile',))
    # return HttpResponse(queryset, content_type='application/xml')
    # Получение списка кортежей с несколькими полями
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    data = DataBaseUser.objects.values_list('service_number', 'last_name', 'first_name', 'surname', 'address',
                                            'birthday', 'gender', 'user_work_profile__job__name').filter(
        user_work_profile__job__type_of_job='2').exclude(is_active=False)

    # Создание корневого элемента XML
    root = ET.Element('root')
    # Добавление комментария
    comment = ET.Comment(get_client_ip(request))
    root.append(comment)
    # Добавление элементов в XML
    for item in data:
        entry = ET.SubElement(root, 'Сотрудник', id=str(item[0]))
        ET.SubElement(entry, 'Табельный_номер').text = str(item[0])
        ET.SubElement(entry, 'Фамилия').text = str(item[1])
        ET.SubElement(entry, 'Имя').text = str(item[2])
        ET.SubElement(entry, 'Отчество').text = str(item[3])
        ET.SubElement(entry, 'Адрес').text = str(item[4])
        ET.SubElement(entry, 'Дата_рождения').text = str(item[5].strftime('%d.%m.%Y'))
        ET.SubElement(entry, 'Пол').text = 'Мужской' if str(item[6]) == 'male' else 'Женский'
        ET.SubElement(entry, 'Должность').text = str(item[7])
        ET.SubElement(entry, 'Признак_1').text = get_type_first(str(item[7]))
        ET.SubElement(entry, 'Признак_2').text = get_type_second(str(item[7]))

    # Преобразование дерева XML в строку
    # xml_string = ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')
    # Добавление заголовка XML
    # xml_with_header = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string
    # Улучшение форматирования XML
    # xml_pretty_string = minidom.parseString(xml_with_header).toprettyxml(indent="    ")
    tree = ET.ElementTree(root)

    # Сериализация XML-документа в строку с форматированием
    def prettify(elem):
        """Возвращает красиво отформатированную XML-строку для Element."""
        rough_string = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    pretty_xml_as_string = prettify(root)

    return HttpResponse(pretty_xml_as_string, content_type='application/xml')
