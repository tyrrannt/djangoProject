from django.urls import path
from . import views
from .views import DocumentsJobDescriptionList, DocumentsJobDescriptionAdd, DocumentsJobDescriptionDetail, \
    DocumentsJobDescriptionUpdate, DocumentsOrderList, DocumentsOrderAdd, DocumentsOrderDetail, DocumentsOrderUpdate

app_name = 'library_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('jobdescription/', DocumentsJobDescriptionList.as_view(), name='jobdescription_list'),
    path('jobdescription/add/', DocumentsJobDescriptionAdd.as_view(), name='jobdescription_add'),
    path('jobdescription/<int:pk>', DocumentsJobDescriptionDetail.as_view(), name='jobdescription'),
    path('jobdescription/<int:pk>/update/', DocumentsJobDescriptionUpdate.as_view(), name='jobdescription_update'),
    path('order/', DocumentsOrderList.as_view(), name='order_list'),
    path('order/add/', DocumentsOrderAdd.as_view(), name='order_add'),
    path('order/<int:pk>', DocumentsOrderDetail.as_view(), name='order'),
    path('order/<int:pk>/update/', DocumentsOrderUpdate.as_view(), name='order_update'),
]
