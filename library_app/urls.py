from django.urls import path
from . import views


app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('help/', views.HelpList.as_view(), name='help_list'),
    path('help/<int:pk>/', views.HelpItem.as_view(), name='help'),

]
