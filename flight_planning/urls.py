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

    # Журнал перемещений воздушных судов
    path('movements/', views.aircraft_movement_list_view, name='aircraft_movement_list'),
    path('movements/add/', views.aircraft_movement_create_view, name='aircraft_movement_add'),
    path('movements/<int:pk>/update/', views.aircraft_movement_update_view, name='aircraft_movement_update'),
    path('movements/<int:pk>/delete/', views.aircraft_movement_delete_view, name='aircraft_movement_delete'),

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
]
