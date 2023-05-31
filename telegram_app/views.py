from django.shortcuts import render
from asgiref.sync import async_to_sync
from loguru import logger

from .webhook import proceed_update
from django.http import HttpResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)
def home(request: HttpRequest):
    return HttpResponse('Hello world')

@csrf_exempt
def telegram(request: HttpRequest):
    # if request.method == 'post':
    try:
        async_to_sync(proceed_update)(request)
        logger.error(f'Функция telegram: {request}')
    except Exception as e:
        logger.error(f'Функция telegram, исключение: {request}')
    return HttpResponse()
    # else:
    #     return HttpResponse(status=403)
