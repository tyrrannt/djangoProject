from django.urls import path

from logistics_app.views import (
    PackageCreateView,
    PackageListView,
    WayBillCreateView,
    WayBillDeleteView,
    WayBillDetailView,
    WayBillListView,
    WayBillUpdateView,
)
from logistics_app.views_docflow import (
    DocFlowAddCommentView,
    DocFlowApproveStepView,
    DocFlowDocumentCreateView,
    DocFlowDocumentDetailView,
    DocFlowDocumentListView,
    DocFlowDocumentTypeCreateView,
    DocFlowDocumentTypeDeleteView,
    DocFlowDocumentTypeListView,
    DocFlowDocumentTypeUpdateView,
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
    # Транспортные накладные и посылки
    path("waybill/", WayBillListView.as_view(), name="waybill_list"),
    path("waybill/add/", WayBillCreateView.as_view(), name="waybill_add"),
    path("waybill/<int:pk>/", WayBillDetailView.as_view(), name="waybill_detail"),
    path("waybill/<int:pk>/update/", WayBillUpdateView.as_view(), name="waybill_update"),
    path("waybill/<int:pk>/delete/", WayBillDeleteView.as_view(), name="waybill_delete"),
    path("package/", PackageListView.as_view(), name="package_list"),
    path("package/add/", PackageCreateView.as_view(), name="package_add"),

    # Электронный документооборот (СЭД)
    path("docflow/", DocFlowDocumentListView.as_view(), name="docflow_list"),
    path("docflow/add/", DocFlowDocumentCreateView.as_view(), name="docflow_create"),
    path("docflow/<uuid:pk>/", DocFlowDocumentDetailView.as_view(), name="docflow_detail"),
    path("docflow/<uuid:pk>/start/", DocFlowStartApprovalView.as_view(), name="docflow_start"),
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
