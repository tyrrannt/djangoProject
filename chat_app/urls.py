from django.urls import path
from . import views

app_name = 'chat_app'

urlpatterns = [
    # path('', views.ContractList.as_view(), name='index'),
    path('<str:room_name>/', views.room, name='room'),
]
