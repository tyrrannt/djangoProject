# tasks_app/urls.py
from django.urls import path
from .views import TaskListView, TaskCreateView, TaskUpdateView, TaskDeleteView, TaskDetailView, create_task_ajax, \
    upload_files_ajax, delete_file_ajax, TaskStatusUpdateView

app_name = 'tasks_app'
urlpatterns = [
    path('', TaskListView.as_view(), name='task-list'),
    path('create/', TaskCreateView.as_view(), name='task-create'),
    path('<int:pk>/', TaskDetailView.as_view(), name='task-detail'),  # ✅ ДОБАВЛЕНО
    path('<int:pk>/update/', TaskUpdateView.as_view(), name='task-update'),
    path('<int:pk>/delete/', TaskDeleteView.as_view(), name='task-delete'),
    path('<int:pk>/status/', TaskStatusUpdateView.as_view(), name='task-status-update'),
    path('create-ajax/', create_task_ajax, name='task-create-ajax'),
    path('upload-files/', upload_files_ajax, name='upload-files-ajax'),
    path('delete-file/', delete_file_ajax, name='delete-file-ajax'),
]
