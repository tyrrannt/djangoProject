from django.urls import path
from . import views
from .views import PortalPropertyList, test_1c_odata_request, get_1c_metadata

app_name = 'administration_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('property/', PortalPropertyList.as_view(), name='property_list'),
    path('property/task/run/', views.PortalPropertyTaskRunView.as_view(), name='property_task_run'),
    path('property/task/status/<str:task_id>/', views.PortalPropertyTaskStatusView.as_view(), name='property_task_status'),
    path('property/api/permissions-audit/', views.portal_permissions_audit_api, name='permissions_audit_api'),
    path('property/api/promote-extra-groups/', views.portal_promote_extra_groups_api, name='promote_extra_groups_api'),
    path('property/api/user-permissions/<int:user_id>/', views.portal_user_permissions_api, name='user_permissions_api'),
    path('property/api/manage-personal-group/', views.portal_manage_personal_group_api, name='manage_personal_group_api'),
    path('json/', views.import_data, name='json'),
    path('monitoring/', views.system_monitor, name='monitoring'),
    path('monitoring/api/data/', views.system_monitor_data_api, name='monitoring_api_data'),
    path('monitoring/api/security/unban/', views.system_monitor_unban_ip_api, name='monitoring_api_unban_ip'),
    path('odata/', views.odata_request, name='1c_odata_request'),
    path('generate-odata/', views.generate_1c_odata_request),
    path('test-odata/', test_1c_odata_request, name='test_1c_odata_request'),
    path('get-metadata/', get_1c_metadata, name='get_1c_metadata'),
    path('api/app-version/', views.get_app_version, name='get_app_version'),
    path('ssl-converter/', views.ssl_cert_converter_view, name='ssl_cert_converter'),
    path('ssl-converter/inspect/', views.ssl_cert_inspect_api, name='ssl_cert_inspect_api'),
    path('ssl-converter/demo/', views.ssl_cert_demo_api, name='ssl_cert_demo_api'),
    path('my-ip/', views.check_my_ip, name='check_my_ip'),
    path('terminal/', views.web_terminal_view, name='web_terminal'),
    path('celery/', views.celery_monitor_view, name='celery_monitor'),
    path('celery/api/data/', views.celery_monitor_data_api, name='celery_monitor_api_data'),
    path('celery/api/run/', views.celery_task_run_api, name='celery_api_run'),
    path('celery/api/revoke/', views.celery_task_revoke_api, name='celery_api_revoke'),
    path('celery/api/detail/<str:task_id>/', views.celery_task_detail_api, name='celery_api_detail'),
    path('celery/api/purge/', views.celery_queue_purge_api, name='celery_api_purge'),
    path('celery/api/ping/', views.celery_workers_ping_api, name='celery_api_ping'),
]
