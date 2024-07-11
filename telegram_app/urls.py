from django.urls import path

from telegram_app.views import json_view, xml_view

app_name = 'telegram_app'
urlpatterns = [
    path('json/', json_view, name='json'),
    path('xml/', xml_view, name='xml'),
    # path(WEBHOOK_PATH, telegram, name='webhook'),
]
