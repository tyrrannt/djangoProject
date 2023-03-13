from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import DetailView, UpdateView, ListView, CreateView
from contracts_app.models import TypeDocuments
from customers_app.models import DataBaseUser, AccessLevel, Division
from django.urls import reverse_lazy



# Create your views here.

def index(request):
    #return render(request, 'library_app/base.html')
    return redirect('/users/login/')


def show_403(request, exception=None):
    return render(request, 'library_app/403.html')

def show_404(request, exception=None):
    return render(request, 'library_app/404.html')
