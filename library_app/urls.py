from django.urls import path
from . import views
from .views import DocumentsList, DocumentsAdd, DocumentsDetail, DocumentsUpdate

app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('documents/', DocumentsList.as_view(), name='documents_list'),
    path('documents/add/', DocumentsAdd.as_view(), name='documents_add'),
    path('documents/<int:pk>', DocumentsDetail.as_view(), name='documents'),
    path('documents/<int:pk>/update/', DocumentsUpdate.as_view(), name='documents_update'),
]
