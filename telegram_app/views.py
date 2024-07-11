import json

from django.shortcuts import render


def home(request):
    dict_obj = {
        '1': {
            'first_name': 'Иванов',
            'last_name': 'Сергей',
            'surname': 'Андреевич',
            'email': 'ivanov@barkol.ru',
            'phone': '88008008080',
            'address': 'Волгоград',
            'birthday': '10.10.1980',
            'gender': 'мужской',
        },
        '2': {
            'first_name': 'Каплин',
            'last_name': 'Михаил',
            'surname': 'Вениаминович',
            'email': 'kaplin@barkol.ru',
            'phone': '88008008080',
            'address': 'Москва',
            'birthday': '10.10.1970',
            'gender': 'мужской',
        },
    }
    return render(request, 'telegram_app/home.html',
                  context={'dict_obj': json.dumps(dict_obj, ensure_ascii=False, indent=4)})
