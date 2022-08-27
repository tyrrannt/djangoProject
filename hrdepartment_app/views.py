from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import ListView

from hrdepartment_app.models import Medical


# Create your views here.

class MedicalExamination(LoginRequiredMixin, ListView):
    model = Medical

