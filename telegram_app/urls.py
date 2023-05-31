from django.urls import path
from .views import home, telegram
from djangoProject.settings import WEBHOOK_PATH
app_name = 'telegram_app'
urlpatterns = [
    path('', home, name='home'),
    path(WEBHOOK_PATH, telegram, name='webhook'),
]