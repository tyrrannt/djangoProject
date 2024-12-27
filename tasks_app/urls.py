from django.urls import path
from .views import TaskListView, TaskCreateView, TaskUpdateView, TaskDeleteView, create_task_ajax, upload_files_ajax

app_name = 'tasks_app'
urlpatterns = [
    path('', TaskListView.as_view(), name='task-list'),
    path('create/', TaskCreateView.as_view(), name='task-create'),
    path('<int:pk>/update/', TaskUpdateView.as_view(), name='task-update'),
    path('<int:pk>/delete/', TaskDeleteView.as_view(), name='task-delete'),
    path('create-ajax/', create_task_ajax, name='task-create-ajax'),  # AJAX-маршрут
    path('upload-files/', upload_files_ajax, name='upload-files-ajax'),
]

