from django.urls import path
from . import views
from .views import MedicalExamination, MedicalExaminationAdd, MedicalExaminationUpdate, OfficialMemoList, \
    OfficialMemoAdd, OfficialMemoUpdate, ApprovalOficialMemoProcessList, ApprovalOficialMemoProcessAdd, \
    ApprovalOficialMemoProcessUpdate, BusinessProcessDirectionList, BusinessProcessDirectionAdd, \
    BusinessProcessDirectionUpdate, ReportApprovalOficialMemoProcessList, MedicalOrganisationList, \
    MedicalOrganisationAdd, MedicalOrganisationUpdate

app_name = 'hrdepartment_app'

urlpatterns = [
    # path('', views.index, name='index'),
    path('medical/', MedicalExamination.as_view(), name='medical_list'),
    path('medical/add/', MedicalExaminationAdd.as_view(), name='medical_add'),
    path('medical/<int:pk>/update/', MedicalExaminationUpdate.as_view(), name='medical_update'),
    path('medicalorg/', MedicalOrganisationList.as_view(), name='medicalorg_list'),
    path('medicalorg/add/', MedicalOrganisationAdd.as_view(), name='medicalorg_add'),
    path('medicalorg/update/<int:pk>/', MedicalOrganisationUpdate.as_view(), name='medicalorg_update'),
    path('memo/', OfficialMemoList.as_view(), name='memo_list'),
    path('memo/add/', OfficialMemoAdd.as_view(), name='memo_add'),
    path('memo/<int:pk>/update/', OfficialMemoUpdate.as_view(), name='memo_update'),
    path('bpmemo/', ApprovalOficialMemoProcessList.as_view(), name='bpmemo_list'),
    path('bpmemo/add/', ApprovalOficialMemoProcessAdd.as_view(), name='bpmemo_add'),
    path('bpmemo/<int:pk>/update/', ApprovalOficialMemoProcessUpdate.as_view(), name='bpmemo_update'),
    path('bpmemo/report/', ReportApprovalOficialMemoProcessList.as_view(), name='bpmemo_report'),
    path('bptrip/', BusinessProcessDirectionList.as_view(), name='bptrip_list'),
    path('bptrip/add/', BusinessProcessDirectionAdd.as_view(), name='bptrip_add'),
    path('bptrip/<int:pk>/update/', BusinessProcessDirectionUpdate.as_view(), name='bptrip_update'),
]
