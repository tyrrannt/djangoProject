from django.urls import path
from . import views
from .views import PortalPropertyList

app_name = 'administration_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('property/', PortalPropertyList.as_view(), name='property_list'),
    path('json/', views.import_data, name='json'),

]
