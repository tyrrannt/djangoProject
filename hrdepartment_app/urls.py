from django.urls import path
from . import views
from .views import MedicalExamination, MedicalExaminationAdd, MedicalExaminationUpdate, OfficialMemoList, \
    OfficialMemoAdd, OfficialMemoUpdate

app_name = 'hrdepartment_app'

urlpatterns = [
    # path('', views.index, name='index'),
    path('medical/', MedicalExamination.as_view(), name='medical_list'),
    path('medical/add/', MedicalExaminationAdd.as_view(), name='medical_add'),
    path('medical/<int:pk>/update/', MedicalExaminationUpdate.as_view(), name='medical_update'),
    path('memo/', OfficialMemoList.as_view(), name='memo_list'),
    path('memo/add/', OfficialMemoAdd.as_view(), name='memo_add'),
    path('memo/<int:pk>/update/', OfficialMemoUpdate.as_view(), name='memo_update'),
]
