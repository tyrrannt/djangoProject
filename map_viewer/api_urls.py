from django.urls import path
from . import views

urlpatterns = [
    path('', views.get_maps_api, name='get_maps_api'),
]
