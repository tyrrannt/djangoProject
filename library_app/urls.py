from django.urls import path
from . import views


app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('help/', views.HelpList.as_view(), name='help_list'),
    path('help/<int:pk>/', views.HelpItem.as_view(), name='help'),
    path('help/<int:pk>/update/', views.HelpItemUpdate.as_view(), name='help_update'),
    path('help/add/', views.HelpItemAdd.as_view(), name='help_add'),

]
