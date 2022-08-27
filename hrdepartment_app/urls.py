from django.urls import path
from . import views
from .views import MedicalExamination

app_name = 'hrdepartment_app'

urlpatterns = [
    path('medical/', MedicalExamination.as_view(), name='medical_list'),
]
