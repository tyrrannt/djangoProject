from django.urls import path
from . import views

app_name = 'customers_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('register/', views.register, name='register'),
    path('profile/<int:pk>/', views.DataBaseUserProfile.as_view(), name='profile'),
    path('profile/<int:pk>/update/', views.DataBaseUserUpdate.as_view(), name='profile_update'),
]
