from django.urls import path
from . import views

app_name = 'administration_app'

urlpatterns = [
    path('', views.index, name='index'),
]
