"""Маршрутизация URL для приложения tasks_app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views
from .views import (
    TaskCreateView,
    TaskDashboardView,
    TaskDeleteView,
    TaskDetailView,
    TaskDisciplineReportView,
    TaskKanbanView,
    TaskListView,
    TaskStatusUpdateView,
    TaskUpdateView,
    comment_add_ajax,
    create_task_ajax,
    delete_file_ajax,
    subtask_add_ajax,
    subtask_delete_ajax,
    subtask_toggle_ajax,
    task_delegate_ajax,
    task_discipline_export_excel_view,
    task_kanban_move_ajax,
    task_status_action_ajax,
    upload_files_ajax,
)

app_name = 'tasks_app'

router_v1 = DefaultRouter()
router_v1.register(r'tasks', api_views.TaskViewSet, basename='api_task_v1')
router_v1.register(r'categories', api_views.CategoryViewSet, basename='api_category_v1')

router_v2 = DefaultRouter()
router_v2.register(r'tasks', api_views.TaskViewSet, basename='api_task_v2')
router_v2.register(r'categories', api_views.CategoryViewSet, basename='api_category_v2')

urlpatterns = [
    # REST API v1 & v2
    path('api/v1/', include(router_v1.urls)),
    path('api/v2/', include(router_v2.urls)),
    path('api/v2/reports/discipline/', api_views.DisciplineReportAPIView.as_view(), name='api-discipline-report'),

    # Основные представления: Календарь, Канбан, Дашборд, Аналитика
    path('', TaskListView.as_view(), name='task-list'),
    path('dashboard/', TaskDashboardView.as_view(), name='task-dashboard'),
    path('kanban/', TaskKanbanView.as_view(), name='task-kanban'),
    path('reports/discipline/', TaskDisciplineReportView.as_view(), name='task-discipline-report'),
    path('reports/discipline/excel/', task_discipline_export_excel_view, name='task-discipline-export-excel'),

    # CRUD задач
    path('create/', TaskCreateView.as_view(), name='task-create'),
    path('<int:pk>/', TaskDetailView.as_view(), name='task-detail'),
    path('<int:pk>/update/', TaskUpdateView.as_view(), name='task-update'),
    path('<int:pk>/delete/', TaskDeleteView.as_view(), name='task-delete'),
    path('<int:pk>/status/', TaskStatusUpdateView.as_view(), name='task-status-update'),

    # AJAX / Workflow операции
    path('<int:pk>/status-action/', task_status_action_ajax, name='task-status-action-ajax'),
    path('<int:pk>/delegate-ajax/', task_delegate_ajax, name='task-delegate-ajax'),
    path('kanban-move/', task_kanban_move_ajax, name='task-kanban-move-ajax'),
    path('create-ajax/', create_task_ajax, name='task-create-ajax'),
    path('upload-files/', upload_files_ajax, name='upload-files-ajax'),
    path('delete-file/', delete_file_ajax, name='delete-file-ajax'),

    # Чек-листы и подзадачи
    path('subtasks/add/', subtask_add_ajax, name='subtask-add-ajax'),
    path('subtasks/toggle/', subtask_toggle_ajax, name='subtask-toggle-ajax'),
    path('subtasks/delete/', subtask_delete_ajax, name='subtask-delete-ajax'),

    # Комментарии и обсуждение
    path('comments/add/', comment_add_ajax, name='comment-add-ajax'),
]
