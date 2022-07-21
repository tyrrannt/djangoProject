from django.urls import path
from . import views

app_name = 'contracts_app'

urlpatterns = [
    path('', views.ContractList.as_view(), name='index'),
    path('create/', views.ContractAdd.as_view(), name='create'),
    path('<int:pk>/', views.ContractDetail.as_view(), name='detail'),
    path('<int:pk>/update/', views.ContractUpdate.as_view(), name='update'),
    path('<int:pk>/postadd/', views.ContractPostAdd.as_view(), name='post_add'),
    path('<int:pk>/posts/', views.ContractPostList.as_view(), name='post_list'),
    path('posts/del/<int:pk>/', views.ContractPostDelete.as_view(), name='post_del'),
]
