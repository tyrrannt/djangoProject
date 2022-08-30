from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView
from customers_app.models import DataBaseUser
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

from library_app.forms import DocumentsAddForm, DocumentsUpdateForm
from library_app.models import Documents


# Create your views here.

def index(request):
    return render(request, 'library_app/base.html')


class DocumentsList(LoginRequiredMixin, ListView):
    template_name = ''
    model = Documents


class DocumentsAdd(LoginRequiredMixin, CreateView):
    template_name = ''
    model = Documents
    form_class = DocumentsAddForm


class DocumentsDetail(LoginRequiredMixin, DetailView):
    template_name = ''
    model = Documents


class DocumentsUpdate(LoginRequiredMixin, UpdateView):
    template_name = ''
    model = Documents
    form_class = DocumentsUpdateForm