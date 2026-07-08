from django.urls import path
from finance_app.views import (
    DashboardView, PaymentCalendarView, ReportsListView, ExportReportView,
    OverdraftListView, OverdraftDetailView, KeyRateSettingsView,
    OverdraftCreateView, OverdraftUpdateView, OverdraftDeleteView,
    CreditTrancheUpdateView, CreditTrancheDeleteView,
    CreditPaymentUpdateView, CreditPaymentDeleteView,
    KeyRateUpdateView, KeyRateDeleteView
)

app_name = "finance"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("calendar/", PaymentCalendarView.as_view(), name="calendar"),
    path("reports/", ReportsListView.as_view(), name="reports_list"),
    path("reports/<str:report_type>/export/", ExportReportView.as_view(), name="export_report"),
    path("overdrafts/", OverdraftListView.as_view(), name="overdraft_list"),
    path("overdrafts/create/", OverdraftCreateView.as_view(), name="overdraft_create"),
    path("overdrafts/<int:pk>/", OverdraftDetailView.as_view(), name="overdraft_detail"),
    path("overdrafts/<int:pk>/update/", OverdraftUpdateView.as_view(), name="overdraft_update"),
    path("overdrafts/<int:pk>/delete/", OverdraftDeleteView.as_view(), name="overdraft_delete"),
    path("overdrafts/tranche/<int:pk>/update/", CreditTrancheUpdateView.as_view(), name="tranche_update"),
    path("overdrafts/tranche/<int:pk>/delete/", CreditTrancheDeleteView.as_view(), name="tranche_delete"),
    path("overdrafts/payment/<int:pk>/update/", CreditPaymentUpdateView.as_view(), name="payment_update"),
    path("overdrafts/payment/<int:pk>/delete/", CreditPaymentDeleteView.as_view(), name="payment_delete"),
    path("settings/key-rates/", KeyRateSettingsView.as_view(), name="key_rates"),
    path("settings/key-rates/<int:pk>/update/", KeyRateUpdateView.as_view(), name="key_rate_update"),
    path("settings/key-rates/<int:pk>/delete/", KeyRateDeleteView.as_view(), name="key_rate_delete"),
]
