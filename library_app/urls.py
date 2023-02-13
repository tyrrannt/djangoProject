from django.urls import path
from . import views
from .views import DocumentsJobDescriptionList, DocumentsJobDescriptionAdd, DocumentsJobDescriptionDetail, \
    DocumentsJobDescriptionUpdate

app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('jobdescription/', DocumentsJobDescriptionList.as_view(), name='jobdescription_list'),
    path('jobdescription/add/', DocumentsJobDescriptionAdd.as_view(), name='jobdescription_add'),
    path('jobdescription/<int:pk>', DocumentsJobDescriptionDetail.as_view(), name='jobdescription'),
    path('jobdescription/<int:pk>/update/', DocumentsJobDescriptionUpdate.as_view(), name='jobdescription_update'),
]
