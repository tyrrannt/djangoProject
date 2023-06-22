from django.urls import path
from . import views
from .views import MedicalExamination, MedicalExaminationAdd, MedicalExaminationUpdate, OfficialMemoList, \
    OfficialMemoAdd, OfficialMemoUpdate, ApprovalOficialMemoProcessList, ApprovalOficialMemoProcessAdd, \
    ApprovalOficialMemoProcessUpdate, BusinessProcessDirectionList, BusinessProcessDirectionAdd, \
    BusinessProcessDirectionUpdate, ReportApprovalOficialMemoProcessList, MedicalOrganisationList, \
    MedicalOrganisationAdd, MedicalOrganisationUpdate, PurposeList, PurposeAdd, PurposeUpdate, \
    DocumentsJobDescriptionList, DocumentsJobDescriptionAdd, DocumentsJobDescriptionDetail, \
    DocumentsJobDescriptionUpdate, DocumentsOrderList, DocumentsOrderAdd, DocumentsOrderDetail, DocumentsOrderUpdate, \
    PlaceProductionActivityList, PlaceProductionActivityAdd, PlaceProductionActivityDetail, \
    PlaceProductionActivityUpdate, ReportCardList, OfficialMemoDetail, \
    ApprovalOficialMemoProcessCancel, ReportCardDetail, ReportCardAdd, ReportCardUpdate, ReportCardDetailFact, \
    ReportCardListManual, ProvisionsList, ProvisionsAdd, ProvisionsDetail, ProvisionsUpdate, ReportCardListAdmin

app_name = 'hrdepartment_app'

urlpatterns = [
    # path('', views.index, name='index'),
    path('medical/', MedicalExamination.as_view(), name='medical_list'),
    path('medical/add/', MedicalExaminationAdd.as_view(), name='medical_add'),
    path('medical/<int:pk>/update/', MedicalExaminationUpdate.as_view(), name='medical_update'),
    path('medicalorg/', MedicalOrganisationList.as_view(), name='medicalorg_list'),
    path('medicalorg/add/', MedicalOrganisationAdd.as_view(), name='medicalorg_add'),
    path('medicalorg/<int:pk>/update/', MedicalOrganisationUpdate.as_view(), name='medicalorg_update'),
    path('memo/', OfficialMemoList.as_view(), name='memo_list'),
    path('memo/add/', OfficialMemoAdd.as_view(), name='memo_add'),
    path('memo/<int:pk>/', OfficialMemoDetail.as_view(), name='memo'),
    path('memo/<int:pk>/update/', OfficialMemoUpdate.as_view(), name='memo_update'),
    path('bpmemo/', ApprovalOficialMemoProcessList.as_view(), name='bpmemo_list'),
    path('bpmemo/add/', ApprovalOficialMemoProcessAdd.as_view(), name='bpmemo_add'),
    path('bpmemo/<int:pk>/update/', ApprovalOficialMemoProcessUpdate.as_view(), name='bpmemo_update'),
    path('bpmemo/report/', ReportApprovalOficialMemoProcessList.as_view(), name='bpmemo_report'),
    path('bpmemo/<int:pk>/cancel/', ApprovalOficialMemoProcessCancel.as_view(), name='bpmemo_cancel'),
    path('bptrip/', BusinessProcessDirectionList.as_view(), name='bptrip_list'),
    path('bptrip/add/', BusinessProcessDirectionAdd.as_view(), name='bptrip_add'),
    path('bptrip/<int:pk>/update/', BusinessProcessDirectionUpdate.as_view(), name='bptrip_update'),
    path('purpose/', PurposeList.as_view(), name='purpose_list'),
    path('purpose/add/', PurposeAdd.as_view(), name='purpose_add'),
    path('purpose/<int:pk>/update/', PurposeUpdate.as_view(), name='purpose_update'),
    path('jobdescription/', DocumentsJobDescriptionList.as_view(), name='jobdescription_list'),
    path('jobdescription/add/', DocumentsJobDescriptionAdd.as_view(), name='jobdescription_add'),
    path('jobdescription/<int:pk>/', DocumentsJobDescriptionDetail.as_view(), name='jobdescription'),
    path('jobdescription/<int:pk>/update/', DocumentsJobDescriptionUpdate.as_view(), name='jobdescription_update'),
    path('order/', DocumentsOrderList.as_view(), name='order_list'),
    path('order/add/', DocumentsOrderAdd.as_view(), name='order_add'),
    path('order/<int:pk>/', DocumentsOrderDetail.as_view(), name='order'),
    path('order/<int:pk>/update/', DocumentsOrderUpdate.as_view(), name='order_update'),
    path('place/', PlaceProductionActivityList.as_view(), name='place_list'),
    path('place/add/', PlaceProductionActivityAdd.as_view(), name='place_add'),
    path('place/<int:pk>/', PlaceProductionActivityDetail.as_view(), name='place'),
    path('place/<int:pk>/update/', PlaceProductionActivityUpdate.as_view(), name='place_update'),
    path('report/', ReportCardList.as_view(), name='reportcard_list'),
    path('report/list/', ReportCardListManual.as_view(), name='reportcard_listmanual'),
    path('report/admin/', ReportCardListAdmin.as_view(), name='reportcard_listadmin'),
    path('report/detail/', ReportCardDetail.as_view(), name='reportcard_detail'),
    path('report/fact/', ReportCardDetailFact.as_view(), name='reportcard_detail_fact'),
    path('report/<int:pk>/update/', ReportCardUpdate.as_view(), name='reportcard_update'),
    path('report/add/', ReportCardAdd.as_view(), name='reportcard_add'),
    path('provisions/', ProvisionsList.as_view(), name='provisions_list'),
    path('provisions/add/', ProvisionsAdd.as_view(), name='provisions_add'),
    path('provisions/<int:pk>/', ProvisionsDetail.as_view(), name='provisions'),
    path('provisions/<int:pk>/update/', ProvisionsUpdate.as_view(), name='provisions_update'),
]
