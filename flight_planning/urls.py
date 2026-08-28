# flight_planning/urls.py
from django.urls import path, include
from . import views, api_views

app_name = 'flight_planning'

api_urlpatterns = [
    path('my-schedule/', api_views.MyScheduleAPIView.as_view(), name='api_my_schedule'),
    path('mpds/', api_views.MPDListAPIView.as_view(), name='api_mpd_list'),
]

urlpatterns = [
    # Главная страница с таблицей
    path('', views.planning_table, name='planning_table'),

    # Личный график пилота
    path('my-schedule/', views.my_schedule_view, name='my_schedule'),

    # Отчеты
    path('reports/utilization/', views.personnel_utilization_report_view, name='flight_personnel_utilization_report'),
    path('reports/basing/', views.aircraft_basing_report_view, name='aircraft_basing_report'),

    # Журнал перемещений воздушных судов
    path('movements/', views.aircraft_movement_list_view, name='aircraft_movement_list'),
    path('movements/add/', views.aircraft_movement_create_view, name='aircraft_movement_add'),
    path('movements/<int:pk>/update/', views.aircraft_movement_update_view, name='aircraft_movement_update'),
    path('movements/<int:pk>/delete/', views.aircraft_movement_delete_view, name='aircraft_movement_delete'),

    # Документы расстановки экипажей (версионирование и утверждение)
    path('documents/', views.document_list_view, name='document_list'),
    path('documents/create/', views.document_create_view, name='document_create'),
    path('documents/<int:pk>/', views.document_detail_view, name='document_detail'),
    path('documents/<int:pk>/print/', views.document_print_view, name='document_print'),
    path('documents/<int:pk>/approve/', views.document_approve_view, name='document_approve'),

    # Периодические проверки персонала (Журнал, Матрица, Справочники)
    path('checks/', views.periodic_check_list_view, name='periodic_check_list'),
    path('checks/add/', views.periodic_check_create_view, name='periodic_check_create'),
    path('checks/<int:pk>/update/', views.periodic_check_update_view, name='periodic_check_update'),
    path('checks/<int:pk>/delete/', views.periodic_check_delete_view, name='periodic_check_delete'),
    path('checks/types/add/', views.periodic_check_type_create_view, name='periodic_check_type_create'),
    path('checks/types/<int:pk>/update/', views.periodic_check_type_update_view, name='periodic_check_type_update'),
    path('checks/types/<int:pk>/delete/', views.periodic_check_type_delete_view, name='periodic_check_type_delete'),

    # Состояния и статусы сотрудников (Отпуск, Больничный, Резерв, КПК, ВЛЭК)
    path('statuses/', views.employee_status_list_view, name='employee_status_list'),
    path('statuses/add/', views.employee_status_create_view, name='employee_status_create'),
    path('statuses/<int:pk>/update/', views.employee_status_update_view, name='employee_status_update'),
    path('statuses/<int:pk>/delete/', views.employee_status_delete_view, name='employee_status_delete'),
    path('statuses/types/add/', views.employee_status_type_create_view, name='employee_status_type_create'),
    path('statuses/types/<int:pk>/update/', views.employee_status_type_update_view, name='employee_status_type_update'),
    path('statuses/types/<int:pk>/delete/', views.employee_status_type_delete_view, name='employee_status_type_delete'),
    path('api/employee-statuses/<int:pilot_id>/', views.get_pilot_employee_statuses_api, name='get_pilot_employee_statuses_api'),

    # API v1 (REST)
    path('api/v1/', include(api_urlpatterns)),

    # Существующие API эндпоинты (для веб-интерфейса)
    path('api/assignments/', views.get_assignments_api, name='get_assignments'),
    path('api/my-assignments/', views.get_my_assignments_api, name='get_my_assignments'),
    path('api/assign/', views.assign_pilot_api, name='assign_pilot'),
    path('api/resolve-conflict/', views.resolve_conflict_api, name='resolve_conflict'),
    path('api/remove/', views.remove_assignments_api, name='remove_assignments'),
    path('api/pilot-job-info/', views.get_pilot_job_info, name='get_pilot_job_info'),
    path('api/aircraft-locations/', views.get_aircraft_locations_api, name='get_aircraft_locations_api'),
    path('api/pilot-checks/<int:pilot_id>/', views.get_pilot_checks_api, name='get_pilot_checks_api'),
    path('api/calculate-check-date/', views.calculate_check_date_api, name='calculate_check_date_api'),
    path('api/check-history/', views.get_check_history_api, name='get_check_history_api'),
    path('api/employee-checks/<int:employee_id>/assignments/', views.get_employee_check_assignments_api, name='get_employee_check_assignments_api'),
    path('api/employee-checks/assignments/save/', views.save_employee_check_assignments_api, name='save_employee_check_assignments_api'),

    # API для работы с экипажами
    path('api/crew/save/', views.save_crew_api, name='save_crew_api'),
    path('api/crew/<int:crew_id>/', views.get_crew_detail_api, name='get_crew_detail_api'),
    path('api/crew/<int:crew_id>/notes/', views.get_crew_notes_api, name='get_crew_notes_api'),
    path('api/crew/<int:crew_id>/notes/add/', views.save_crew_note_api, name='save_crew_note_api'),
    path('api/crew/notes/<int:note_id>/delete/', views.delete_crew_note_api, name='delete_crew_note_api'),
    path('api/crew/delete/', views.delete_crew_api, name='delete_crew_api'),
    path('api/crew/day-info/', views.get_day_crew_info_api, name='get_day_crew_info_api'),
    path('api/crew/validate/', views.validate_crew_api, name='validate_crew_api'),
    path('api/crew/add-member/', views.add_member_to_crew_api, name='add_member_to_crew_api'),
    path('api/crew/batch-swap-aircraft/', views.batch_swap_aircraft_api, name='batch_swap_aircraft_api'),
]
