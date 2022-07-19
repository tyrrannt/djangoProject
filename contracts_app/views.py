from django.shortcuts import render, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView, DeleteView

from contracts_app.models import Contract, Posts
from contracts_app.forms import ContractsAddForm, ContractsPostAddForm
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
    """
    Просмотр договора.
    """
    model = Contract

    def get_context_data(self, **kwargs):
        context = super(ContractDetail, self).get_context_data(**kwargs)
        # Выбираем из таблицы Posts все записи относящиеся к текущему договору
        post = Posts.objects.filter(contract_number=self.object.pk)
        # Формируем заголовок страницы и передаем в контекст
        context['title'] = title = 'Договор №' + self.object.contract_number + ' от ' + str(self.object.date_conclusion)
        # Передаем найденные записи в контекст
        context['posts'] = post
        return context

class ContractPostAdd(CreateView):
    model = Posts
    form_class = ContractsPostAddForm
    success_url = reverse_lazy('contracts_app:index')

class ContractPostList(ListView):
    model = Posts
    #queryset = Posts.objects.filter(contract_number=)

    def get_queryset(self):
        qs = self.model.objects.all()
        search = self.request.GET.get('cn')
        if search:
            qs = qs.filter(contract_number=search)
        print(search)
        return qs


class ContractPostDelete(DeleteView):
    model = Posts

