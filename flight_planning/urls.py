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

    # API v1 (REST)
    path('api/v1/', include(api_urlpatterns)),

    # Существующие API эндпоинты (для веб-интерфейса)
    path('api/assignments/', views.get_assignments_api, name='get_assignments'),
    path('api/my-assignments/', views.get_my_assignments_api, name='get_my_assignments'),
    path('api/assign/', views.assign_pilot_api, name='assign_pilot'),
    path('api/resolve-conflict/', views.resolve_conflict_api, name='resolve_conflict'),
    path('api/remove/', views.remove_assignments_api, name='remove_assignments'),
    path('api/pilot-job-info/', views.get_pilot_job_info, name='get_pilot_job_info'),
]
