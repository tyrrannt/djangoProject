# password_manager/urls.py
"""
Маршрутизация приложения password_manager.

Использует app_name для изоляции namespace в проекте.
Все пути следуют RESTful-конвенциям Django и поддерживают
стандартные CRUD-операции через Class-Based Views.
"""

from django.urls import path
from . import views

app_name = 'password_manager'

urlpatterns = [
    # Настройка ключевой фразы (обязательный шаг перед работой)
    path('key/setup/', views.KeySetupView.as_view(), name='key_setup'),

    # CRUD для групп паролей
    path('groups/tree-data/', views.GroupTreeDataView.as_view(), name='group_tree_data'),
    path('groups/', views.GroupListView.as_view(), name='group_list'),
    path('groups/create/', views.GroupCreateView.as_view(), name='group_create'),
    path('groups/<int:pk>/update/', views.GroupUpdateView.as_view(), name='group_update'),
    path('groups/<int:pk>/delete/', views.GroupDeleteView.as_view(), name='group_delete'),

    # CRUD для записей паролей
    path('', views.PasswordListView.as_view(), name='password_list'),
    path('create/', views.PasswordCreateView.as_view(), name='password_create'),
    path('<int:pk>/', views.PasswordDetailView.as_view(), name='password_detail'),
    path('<int:pk>/update/', views.PasswordUpdateView.as_view(), name='password_update'),
    path('<int:pk>/delete/', views.PasswordDeleteView.as_view(), name='password_delete'),

    # История изменений пароля
    path('<int:pk>/history/', views.PasswordHistoryView.as_view(), name='password_history'),

    # Управление общим доступом (совладельцы)
    path('<int:pk>/share/', views.ManageSharedAccessView.as_view(), name='password_share'),

    # Эндпоинт для безопасного получения расшифрованного пароля
    path('<int:pk>/reveal/', views.PasswordRevealView.as_view(), name='password_reveal'),
]
