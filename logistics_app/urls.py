from django.urls import path

from logistics_app.views import WayBillListView

app_name = 'logistics_app'

urlpatterns = [
    # path('', views.index, name='index'),
    path('logistics/', WayBillListView.as_view(), name='logistics_list'),
    ]