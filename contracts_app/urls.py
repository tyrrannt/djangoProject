from django.urls import path
from . import views

app_name = 'contracts_app'

urlpatterns = [
    path('', views.ContractList.as_view(), name='index'),
    path('create/', views.ContractAdd.as_view(), name='create'),
    path('<int:pk>/', views.ContractDetail.as_view(), name='detail'),
]
