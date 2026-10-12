from django.urls import path

from logistics_app.views import (
    WayBillCreateView,
    WayBillDeleteView,
    WayBillDetailView,
    WayBillListView,
    WayBillUpdateView,
)
from logistics_app.views_shipment import (
    PackageAttachTripView,
    PackageCreateView,
    PackageDetailView,
    PackageDetachTripView,
    PackageListView,
    PackageReceiveView,
    PackageSheetPdfView,
    PackageUpdateView,
    ShipmentTripActionView,
    ShipmentTripCreateView,
    ShipmentTripDetailView,
    ShipmentTripListView,
    ShipmentTripUpdateView,
)
from logistics_app.views_docflow import (
    DocFlowAddCommentView,
    DocFlowAddRouteStepView,
    DocFlowApproveStepView,
    DocFlowDeleteRouteStepView,
    DocFlowDocumentCreateView,
    DocFlowDocumentDetailView,
    DocFlowDocumentListView,
    DocFlowDocumentTypeCreateView,
    DocFlowDocumentTypeDeleteView,
    DocFlowDocumentTypeListView,
    DocFlowDocumentTypeUpdateView,
    DocFlowDocumentUpdateView,
    DocFlowRejectView,
    DocFlowRestartRouteView,
    DocFlowReturnReworkView,
    DocFlowRollbackStepView,
    DocFlowRouteTemplateCreateView,
    DocFlowRouteTemplateDeleteView,
    DocFlowRouteTemplateListView,
    DocFlowRouteTemplateUpdateView,
    DocFlowStartApprovalView,
    DocFlowUploadVersionView,
    DocFlowVersionDownloadView,
)

app_name = "logistics_app"

urlpatterns = [
    # Рейсы и доставка автотранспортом на МПД
    path("trips/", ShipmentTripListView.as_view(), name="trip_list"),
    path("trips/add/", ShipmentTripCreateView.as_view(), name="trip_add"),
    path("trips/<int:pk>/", ShipmentTripDetailView.as_view(), name="trip_detail"),
    path("trips/<int:pk>/update/", ShipmentTripUpdateView.as_view(), name="trip_update"),
    path("trips/<int:pk>/action/", ShipmentTripActionView.as_view(), name="trip_action"),

    # Транспортные накладные и посылки
    path("waybill/", WayBillListView.as_view(), name="waybill_list"),
    path("waybill/add/", WayBillCreateView.as_view(), name="waybill_add"),
    path("waybill/<int:pk>/", WayBillDetailView.as_view(), name="waybill_detail"),
    path("waybill/<int:pk>/update/", WayBillUpdateView.as_view(), name="waybill_update"),
    path("waybill/<int:pk>/delete/", WayBillDeleteView.as_view(), name="waybill_delete"),
    path("package/", PackageListView.as_view(), name="package_list"),
    path("package/add/", PackageCreateView.as_view(), name="package_add"),
    path("package/<int:pk>/", PackageDetailView.as_view(), name="package_detail"),
    path("package/<int:pk>/update/", PackageUpdateView.as_view(), name="package_update"),
    path("package/<int:pk>/receive/", PackageReceiveView.as_view(), name="package_receive"),
    path("package/<int:pk>/pdf/", PackageSheetPdfView.as_view(), name="package_sheet_pdf"),
    path("package/<int:pk>/attach-trip/", PackageAttachTripView.as_view(), name="package_attach_trip"),
    path("package/<int:pk>/detach-trip/", PackageDetachTripView.as_view(), name="package_detach_trip"),

    # Электронный документооборот (СЭД)
    path("docflow/", DocFlowDocumentListView.as_view(), name="docflow_list"),
    path("docflow/add/", DocFlowDocumentCreateView.as_view(), name="docflow_create"),
    path("docflow/<uuid:pk>/", DocFlowDocumentDetailView.as_view(), name="docflow_detail"),
    path("docflow/<uuid:pk>/update/", DocFlowDocumentUpdateView.as_view(), name="docflow_update"),
    path("docflow/<uuid:pk>/start/", DocFlowStartApprovalView.as_view(), name="docflow_start"),
    path("docflow/<uuid:pk>/step/add/", DocFlowAddRouteStepView.as_view(), name="docflow_step_add"),
    path("docflow/<uuid:pk>/step/<int:step_id>/delete/", DocFlowDeleteRouteStepView.as_view(), name="docflow_step_delete"),
    path("docflow/<uuid:pk>/approve/", DocFlowApproveStepView.as_view(), name="docflow_approve_step"),
    path("docflow/<uuid:pk>/rollback/", DocFlowRollbackStepView.as_view(), name="docflow_rollback_step"),
    path("docflow/<uuid:pk>/rework/", DocFlowReturnReworkView.as_view(), name="docflow_return_rework"),
    path("docflow/<uuid:pk>/restart/", DocFlowRestartRouteView.as_view(), name="docflow_restart"),
    path("docflow/<uuid:pk>/reject/", DocFlowRejectView.as_view(), name="docflow_reject"),
    path("docflow/<uuid:pk>/upload-version/", DocFlowUploadVersionView.as_view(), name="docflow_upload_version"),
    path("docflow/<uuid:pk>/add-comment/", DocFlowAddCommentView.as_view(), name="docflow_add_comment"),
    path("docflow/version/<int:version_id>/download/", DocFlowVersionDownloadView.as_view(), name="docflow_version_download"),

    # Шаблоны маршрутов согласования
    path("docflow/templates/", DocFlowRouteTemplateListView.as_view(), name="docflow_template_list"),
    path("docflow/templates/add/", DocFlowRouteTemplateCreateView.as_view(), name="docflow_template_add"),
    path("docflow/templates/<int:pk>/update/", DocFlowRouteTemplateUpdateView.as_view(), name="docflow_template_update"),
    path("docflow/templates/<int:pk>/delete/", DocFlowRouteTemplateDeleteView.as_view(), name="docflow_template_delete"),

    # Виды документов СЭД
    path("docflow/types/", DocFlowDocumentTypeListView.as_view(), name="docflow_type_list"),
    path("docflow/types/add/", DocFlowDocumentTypeCreateView.as_view(), name="docflow_type_add"),
    path("docflow/types/<int:pk>/update/", DocFlowDocumentTypeUpdateView.as_view(), name="docflow_type_update"),
    path("docflow/types/<int:pk>/delete/", DocFlowDocumentTypeDeleteView.as_view(), name="docflow_type_delete"),
]
