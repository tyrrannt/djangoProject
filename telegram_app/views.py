import json
from pprint import pprint

from django.db.models import F, ExpressionWrapper, CharField
from django.http import HttpResponse
from django.shortcuts import render
from django.core import serializers

from customers_app.models import DataBaseUser


def json_view(request):
    dict_obj = DataBaseUser.objects.filter(is_active=False)[:3]
    queryset = serializers.serialize('json', dict_obj,
                                     fields=('last_name', 'first_name', 'surname', 'address', 'birthday', 'gender'))
    return HttpResponse(queryset, content_type='application/json')


def get_type_first(job) -> str:
    if str(job).find('Инженер') >= 0:
        return 'Инженер'
    elif str(job).find('Техник') >= 0:
        return 'Техник'
    elif str(job).find('качеству') >= 0:
        return 'ГКК'
    else:
        return ''

def get_type_second(job) -> str:
    if str(job).find('систем') >= 0:
        return 'АиРЭО'
    else:
        return 'ПиД'


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
                                            'birthday', 'gender', 'user_work_profile__job__name').filter(user_work_profile__job__type_of_job='2').exclude(is_active=False)

    # Создание корневого элемента XML
    root = ET.Element('data')

    # Добавление элементов в XML
    for item in data:
        entry = ET.SubElement(root, 'Сотрудник')
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
    xml_string = ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')

    # Улучшение форматирования XML
    xml_pretty_string = minidom.parseString(xml_string).toprettyxml(indent="    ")
    return HttpResponse(xml_pretty_string, content_type='application/xml')
