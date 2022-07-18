from django.shortcuts import render, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView

from contracts_app.models import Contract
from customers_app.models import DataBaseUser, Posts
from contracts_app.forms import ContractsAddForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test


# Create your views here.

# def index(request):
#     return render(request, 'contracts_app/main.html')

class ContractList(ListView):
    """
    Отображение списка договоров
    """
    model = Contract


class ContractAdd(CreateView):
    """
    Создание нового договора
    """
    model = Contract
    form_class = ContractsAddForm
    success_url = reverse_lazy('contracts_app:index')


class ContractDetail(DetailView):
    model = Contract
