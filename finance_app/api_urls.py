from django.urls import path
from .api_views import OverdraftListAPIView

urlpatterns = [
    path('overdrafts/', OverdraftListAPIView.as_view(), name='api_overdraft_list'),
]
