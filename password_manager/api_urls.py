from django.urls import path
from .api_views import PasswordListAPIView

urlpatterns = [
    path('', PasswordListAPIView.as_view(), name='api_password_list'),
]
