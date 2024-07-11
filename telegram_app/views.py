import json

from django.http import HttpResponse
from django.shortcuts import render
from django.core import serializers

from customers_app.models import DataBaseUser


def json_view(request):
    dict_obj = DataBaseUser.objects.filter(is_active=False)
    queryset = serializers.serialize('json', dict_obj,
                                     fields=('first_name', 'last_name', 'surname', 'address', 'birthday', 'gender'))
    return HttpResponse(queryset, content_type='application/json')


def xml_view(request):
    dict_obj = DataBaseUser.objects.filter(is_active=False)
    queryset = serializers.serialize('xml', dict_obj, fields=('first_name', 'last_name','surname', 'address', 'birthday', 'gender'))
    return HttpResponse(queryset, content_type='application/xml')
