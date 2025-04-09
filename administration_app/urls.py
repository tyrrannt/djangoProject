from django.urls import path
from . import views
from .views import PortalPropertyList

app_name = 'administration_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('property/', PortalPropertyList.as_view(), name='property_list'),
    path('json/', views.import_data, name='json'),
    path('monitoring/', views.system_monitor, name='monitoring'),
    path('odata/', views.odata_request, name='1c_odata_request'),
    path('generate-odata/', views.generate_1c_odata_request)

]
