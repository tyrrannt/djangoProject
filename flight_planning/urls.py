# flight_planning/urls.py
from django.urls import path
from . import views

app_name = 'flight_planning'

urlpatterns = [
    # Главная страница с таблицей
    path('', views.planning_table, name='planning_table'),

    # Личный график пилота
    path('my-schedule/', views.my_schedule_view, name='my_schedule'),

    # API эндпоинты
    path('api/assignments/', views.get_assignments_api, name='get_assignments'),
    path('api/my-assignments/', views.get_my_assignments_api, name='get_my_assignments'),
    path('api/assign/', views.assign_pilot_api, name='assign_pilot'),
    path('api/resolve-conflict/', views.resolve_conflict_api, name='resolve_conflict'),
    path('api/remove/', views.remove_assignments_api, name='remove_assignments'),
    path('api/pilot-job-info/', views.get_pilot_job_info, name='get_pilot_job_info'),
]
