from django.urls import path
from . import views

app_name = 'ppequipment_app'

urlpatterns = [
    path('', views.index, name='index'),
    # path('video/', views.video, name='video'),
    # path('help/', views.HelpList.as_view(), name='help_list'),

]
