from django.urls import path
from . import views

app_name = 'map_viewer'

urlpatterns = [
    path('', views.map_index, name='index'),
    path('tile/<int:map_id>/<int:z>/<int:x>/<int:y>/', views.get_tile, name='tile_server'),
]