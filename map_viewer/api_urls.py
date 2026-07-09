from django.urls import path
from . import views

urlpatterns = [
    path('', views.get_maps_api, name='get_maps_api'),
    path('tile/<int:map_id>/<int:z>/<int:x>/<int:y>/', views.api_get_tile, name='api_get_tile'),
]
