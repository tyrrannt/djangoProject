from django.urls import path

from telegram_app.views import home

app_name = 'telegram_app'
urlpatterns = [
    path('', home, name='home'),
    # path(WEBHOOK_PATH, telegram, name='webhook'),
]
