from django.urls import path

from logistics_app.views import (WayBillListView, WayBillCreateView, WayBillUpdateView,
                                 WayBillDetailView, WayBillDeleteView, PackageListView, PackageCreateView)

app_name = 'logistics_app'

urlpatterns = [
    path('waybill/', WayBillListView.as_view(), name='waybill_list'),
    path('waybill/add/', WayBillCreateView.as_view(), name='waybill_add'),
    path('waybill/<int:pk>/', WayBillDetailView.as_view(), name='waybill_detail'),
    path('waybill/<int:pk>/update/', WayBillUpdateView.as_view(), name='waybill_update'),
    path('waybill/<int:pk>/delete/', WayBillDeleteView.as_view(), name='waybill_delete'),
    path('package/', PackageListView.as_view(), name='package_list'),
    path('package/add/', PackageCreateView.as_view(), name='package_add'),
    ]
