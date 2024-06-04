from django.urls import path
from . import views

app_name = 'contracts_app'

urlpatterns = [
    path('', views.ContractList.as_view(), name='index'),
    # path(r'^pdf', views.pdf, name='pdf'),
    path('search/', views.ContractSearch.as_view(), name='search'),
    path('create/', views.ContractAdd.as_view(), name='create'),
    path('<int:pk>/', views.ContractDetail.as_view(), name='detail'),
    path('<int:pk>/update/', views.ContractUpdate.as_view(), name='update'),
    path('<int:pk>/postadd/', views.ContractPostAdd.as_view(), name='post_add'),
    path('<int:pk>/posts/', views.ContractPostList.as_view(), name='post_list'),
    path('posts/del/<int:pk>/', views.ContractPostDelete.as_view(), name='post_del'),
    path('typedocuments/', views.TypeDocumentsList.as_view(), name='typedocuments_list'),
    path('typedocuments/add/', views.TypeDocumentsAdd.as_view(), name='typedocuments_add'),
    path('typedocuments/<int:pk>/', views.TypeDocumentsDetail.as_view(), name='typedocuments'),
    path('typedocuments/<int:pk>/update/', views.TypeDocumentsUpdate.as_view(), name='typedocuments_update'),
    path('typecontracts/', views.TypeContractsList.as_view(), name='typecontracts_list'),
    path('typecontracts/add/', views.TypeContractsAdd.as_view(), name='typecontracts_add'),
    path('typecontracts/<int:pk>/', views.TypeContractsDetail.as_view(), name='typecontracts'),
    path('typecontracts/<int:pk>/update/', views.TypeContractsUpdate.as_view(), name='typecontracts_update'),
    path('typepropertys/', views.TypePropertysList.as_view(), name='typepropertys_list'),
    path('typepropertys/add/', views.TypePropertysAdd.as_view(), name='typepropertys_add'),
    path('typepropertys/<int:pk>/', views.TypePropertysDetail.as_view(), name='typepropertys'),
    path('typepropertys/<int:pk>/update/', views.TypePropertysUpdate.as_view(), name='typepropertys_update'),
    path('estate/', views.EstateList.as_view(), name='estate_list'),
    path('estate/add/', views.EstateAdd.as_view(), name='estate_add'),
    path('estate/<int:pk>/', views.EstateDetail.as_view(), name='estate'),
    path('estate/<int:pk>/update/', views.EstateUpdate.as_view(), name='estate_update'),
    path('check/', views.counteragent_check, name='counteragent_check'),
]
