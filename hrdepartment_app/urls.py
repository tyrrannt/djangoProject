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
    ReportCardListManual, ProvisionsList, ProvisionsAdd, ProvisionsDetail, ProvisionsUpdate, ReportCardListAdmin, \
    ReportCardDelete, ApprovalOficialMemoProcessReportList, OfficialMemoCancel, GuidanceDocumentsList, \
    GuidanceDocumentsAdd, GuidanceDocumentsDetail, GuidanceDocumentsUpdate, CreatingTeamList, CreatingTeamAdd, \
    CreatingTeamDetail, CreatingTeamUpdate, CreatingTeamAgreed, CreatingTeamSetNumber, ExpensesList, expenses_update, \
    ReportCardDetailYear, ReportCardDetailYearXLS, TimeSheetCreateView, TimeSheetDetailView, TimeSheetUpdateView, \
    TimeSheetDeleteView, TimeSheetListView, OutfitCardListView, OutfitCardCreateView, OutfitCardDetailView, \
    OutfitCardUpdateView, OutfitCardDeleteView, ReportCardDetailIAS, filter_outfit_cards, acknowledge_document, \
    unacknowledge_document, seasonality_report, export_seasonality_data, absence_analysis, export_absence_data, \
    employee_absence_details, weekday_analysis, time_distribution, export_time_distribution, \
    ApprovalOficialMemoProcessDetail, management_dashboard, export_trips_csv, BriefingsList, BriefingsAdd, \
    BriefingsDetail, BriefingsUpdate, OperationalList, OperationalAdd, OperationalDetail, OperationalUpdate, \
    GetUserEventsView, BriefingsDelete, DataBaseUserEventList, DataBaseUserEventAdd, DataBaseUserEventDetail, \
    DataBaseUserEventUpdate, DataBaseUserEventDelete

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
    path('memo/<int:pk>/cancel/', OfficialMemoCancel.as_view(), name='memo_cancel'),
    path("memo/get_extension_data/", views.get_extension_data, name="get_extension_data"),
    path('bpmemo/', ApprovalOficialMemoProcessList.as_view(), name='bpmemo_list'),
    path('bpmemo/add/', ApprovalOficialMemoProcessAdd.as_view(), name='bpmemo_add'),
    path('bpmemo/<int:pk>/update/', ApprovalOficialMemoProcessUpdate.as_view(), name='bpmemo_update'),
    path('bpmemo/<int:pk>/', ApprovalOficialMemoProcessDetail.as_view(), name='bpmemo'),
    path('bpmemo/report/', ReportApprovalOficialMemoProcessList.as_view(), name='bpmemo_report'),
    path('bpmemo/month-report/', ApprovalOficialMemoProcessReportList.as_view(), name='bpmemo_month_report'),
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
    path('report/ias/', ReportCardDetailIAS.as_view(), name='reportcard_detail_ias'),
    path('report/year/', ReportCardDetailYear.as_view(), name='reportcard_detail_year'),
    path('report/year-xls/', ReportCardDetailYearXLS.as_view(), name='reportcard_detail_year_xls'),
    path('report/<int:pk>/update/', ReportCardUpdate.as_view(), name='reportcard_update'),
    path('report/<int:pk>/delete/', ReportCardDelete.as_view(), name='reportcard_delete'),
    path('report/add/', ReportCardAdd.as_view(), name='reportcard_add'),
    path('provisions/', ProvisionsList.as_view(), name='provisions_list'),
    path('provisions/add/', ProvisionsAdd.as_view(), name='provisions_add'),
    path('provisions/<int:pk>/', ProvisionsDetail.as_view(), name='provisions'),
    path('provisions/<int:pk>/update/', ProvisionsUpdate.as_view(), name='provisions_update'),

    path('briefings/', BriefingsList.as_view(), name='briefings_list'),
    path('briefings/add/', BriefingsAdd.as_view(), name='briefings_add'),
    path('briefings/<int:pk>/', BriefingsDetail.as_view(), name='briefings'),
    path('briefings/<int:pk>/update/', BriefingsUpdate.as_view(), name='briefings_update'),
    path('briefings/<int:pk>/delete/', BriefingsDelete.as_view(), name='briefings_delete'),

    path('operational/', OperationalList.as_view(), name='operational_list'),
    path('operational/add/', OperationalAdd.as_view(), name='operational_add'),
    path('operational/<int:pk>/', OperationalDetail.as_view(), name='operational'),
    path('operational/<int:pk>/update/', OperationalUpdate.as_view(), name='operational_update'),

    path('guidance_documents/', GuidanceDocumentsList.as_view(), name='guidance_documents_list'),
    path('guidance_documents/add/', GuidanceDocumentsAdd.as_view(), name='guidance_documents_add'),
    path('guidance_documents/<int:pk>/', GuidanceDocumentsDetail.as_view(), name='guidance_documents'),
    path('guidance_documents/<int:pk>/update/', GuidanceDocumentsUpdate.as_view(), name='guidance_documents_update'),
    path('team/', CreatingTeamList.as_view(), name='team_list'),
    path('team/add/', CreatingTeamAdd.as_view(), name='team_add'),
    path('team/<int:pk>/', CreatingTeamDetail.as_view(), name='team'),
    path('team/<int:pk>/update/', CreatingTeamUpdate.as_view(), name='team_update'),
    path('team/<int:pk>/agreed/', CreatingTeamAgreed.as_view(), name='team_agreed'),
    path('team/<int:pk>/number/', CreatingTeamSetNumber.as_view(), name='team_number'),
    path('expenses/', ExpensesList.as_view(), name='expenses_list'),
    path('expenses/<int:pk>/update/', expenses_update, name='expenses_update'),
    path('timesheet/add/', TimeSheetCreateView.as_view(), name='timesheet_add'),
    path('timesheet/get-user-events/', GetUserEventsView.as_view(), name='get_user_events'),
    path('timesheet/<int:pk>/', TimeSheetDetailView.as_view(), name='timesheet'),
    path('timesheet/<int:pk>/update/', TimeSheetUpdateView.as_view(), name='timesheet_update'),
    path('timesheet/<int:pk>/delete/', TimeSheetDeleteView.as_view(), name='timesheet_delete'),
    path('timesheet/', TimeSheetListView.as_view(), name='timesheet_list'),  # Добавляем маршрут для списка табелей
    path('timesheet/filter-outfit-cards/', filter_outfit_cards, name='filter_outfit_cards'),
    path('outfit_cards/', OutfitCardListView.as_view(), name='outfit_card_list'),
    path('outfit_cards/create/', OutfitCardCreateView.as_view(), name='outfit_card_add'),
    path('outfit_cards/<int:pk>/', OutfitCardDetailView.as_view(), name='outfit_card'),
    path('outfit_cards/<int:pk>/update/', OutfitCardUpdateView.as_view(), name='outfit_card_update'),
    path('outfit_cards/<int:pk>/delete/', OutfitCardDeleteView.as_view(), name='outfit_card_delete'),
    path('acknowledge/', acknowledge_document, name='acknowledge_document'),
    path('unacknowledge/', unacknowledge_document, name='unacknowledge_document'),
    path("seasonality-report/", seasonality_report, name="seasonality-report"),
    path("export-seasonality-data/", export_seasonality_data, name="export-seasonality-data"),
    path('absence-analysis/', absence_analysis, name='absence_analysis'),
    path('export-absence-data/', export_absence_data, name='export_absence_data'),
    path('employee-absence-details/<str:username>/', employee_absence_details, name='employee_absence_details'),
    path("weekday-analysis/", weekday_analysis, name="weekday-analysis"),
    path('time-distribution/', time_distribution, name='time_distribution'),
    path("export-time-distribution/", export_time_distribution, name="export-time-distribution"),
    path('dashboard/', management_dashboard, name='management_dashboard'),
    path('dashboard/export/', export_trips_csv, name='export_trips'),

    path('users_events/', DataBaseUserEventList.as_view(), name='users_events_list'),
    path('users_events/add/', DataBaseUserEventAdd.as_view(), name='users_events_add'),
    path('users_events/<int:pk>/', DataBaseUserEventDetail.as_view(), name='users_events'),
    path('users_events/<int:pk>/update/', DataBaseUserEventUpdate.as_view(), name='users_events_update'),
    path('users_events/<int:pk>/delete/', DataBaseUserEventDelete.as_view(), name='users_events_delete'),
]
