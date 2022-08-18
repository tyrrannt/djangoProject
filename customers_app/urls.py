from django.urls import path
from . import views

app_name = 'customers_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('register/', views.SignUpView.as_view(), name='register'),
    path('profile/<int:pk>/', views.DataBaseUserProfile.as_view(), name='profile'),
    path('profile/<int:pk>/post/', views.PostsAddView.as_view(), name='post_add'),
    path('profile/<int:pk>/postslist/', views.PostsListView.as_view(), name='post_list'),
    path('profile/<int:pk>/update/', views.DataBaseUserUpdate.as_view(), name='profile_update'),
    path('counteragent/', views.CounteragentListView.as_view(), name='counteragent_list'),
    path('counteragent/<int:pk>/', views.CounteragentDetail.as_view(), name='counteragent'),
    path('counteragent/<int:pk>/update/', views.CounteragentUpdate.as_view(), name='counteragent_update'),
    path('staff/', views.StaffListView.as_view(), name='staff_list'),
]
