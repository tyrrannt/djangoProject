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
    template_name = 'contracts_app/contract_list.html'

    def post(self, request, *args, **kwargs):
        stuff = request.POST.get('division')
        print(stuff)
        if stuff:
            stuff = self.get_queryset().filter(divisions=stuff)
        else:
            stuff = self.get_queryset().all()
        return render(request, self.template_name, {'object_list': stuff})


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
        slaves = Contract.objects.filter(parent_category=self.object.pk)
        # Формируем заголовок страницы и передаем в контекст
        if self.object.contract_number:
            cn = self.object.contract_number
        else:
            cn = '(без номера)'
        context['title'] = title = 'Договор №' + cn + ' от ' + str(self.object.date_conclusion)
        # Передаем найденные записи в контекст
        context['posts'] = post
        context['slaves'] = slaves
        return context


class ContractPostAdd(CreateView):
    """
    Добавление записи к договору.
    """
    model = Posts
    form_class = ContractsPostAddForm

    def get_success_url(self):
        """
        Переопределяется метод 'get_success_url', для получения номера договора 'pk',
        к которому добавляется запись, для того чтоб вернуться на страницу договора
        :return: Возвращается URL на договор
        """
        pk = self.object.contract_number.pk
        return reverse("contracts_app:detail", kwargs={"pk": pk})


class ContractPostList(ListView):
    """
    Вывод списка записей, относящихся к конкретному договору
    """
    model = Posts

    def get_queryset(self):
        """
        Переопределен метод получения QuerySet. Записи фильтруются исходя из GET запроса, в котором передается
        параметр contract_number.
        :return: Отфильтрованный QuerySet если задан параметр GET, иначе выводит полный список записей  модели Post
        """
        qs = self.model.objects.all()
        search = self.request.GET.get('cn')
        if search:
            qs = qs.filter(contract_number=search)
        return qs


class ContractPostDelete(DeleteView):
    """
    Удаление записи
    """
    model = Posts
