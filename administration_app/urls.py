from django.urls import path
from . import views
from .views import PortalPropertyList, test_1c_odata_request, get_1c_metadata

app_name = 'administration_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('property/', PortalPropertyList.as_view(), name='property_list'),
    path('property/task/run/', views.PortalPropertyTaskRunView.as_view(), name='property_task_run'),
    path('property/task/status/<str:task_id>/', views.PortalPropertyTaskStatusView.as_view(), name='property_task_status'),
    path('json/', views.import_data, name='json'),
    path('monitoring/', views.system_monitor, name='monitoring'),
    path('monitoring/api/data/', views.system_monitor_data_api, name='monitoring_api_data'),
    path('odata/', views.odata_request, name='1c_odata_request'),
    path('generate-odata/', views.generate_1c_odata_request),
    path('test-odata/', test_1c_odata_request, name='test_1c_odata_request'),
    path('get-metadata/', get_1c_metadata, name='get_1c_metadata'),
    path('api/app-version/', views.get_app_version, name='get_app_version'),
]
