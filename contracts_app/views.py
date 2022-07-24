from django.core.paginator import Paginator
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView, DeleteView

from contracts_app.models import Contract, Posts, TypeContract, TypeProperty
from contracts_app.forms import ContractsAddForm, ContractsPostAddForm, ContractsUpdateForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

from contracts_app.utils import GetAllObject

# Create your views here.

# def index(request):
#     return render(request, 'contracts_app/main.html')
from customers_app.models import DataBaseUser, Counteragent, Division


class ContractList(ListView):
    """
    Отображение списка договоров
    """
    model = Contract
    template_name = 'contracts_app/contract_list.html'
    paginate_by = 3

    def get_context_data(self, **kwargs):
        context = super(ContractList, self).get_context_data(**kwargs)
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context


class ContractSearch(ListView):
    template_name_suffix = '_search'
    context_object_name = 'object'
    object_list = None
    paginate_by = 3

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('contracts_app:search'))

    #Работает с GET запросом
    def get_queryset(self):
        qs = Contract.objects.all()
        if self.request.GET:
            return Contract.objects.filter(divisions=int(self.request.GET.get('division')))
        return qs

    # # Работает с POST запросом
    # def get_queryset(self):
    #     qs = Contract.objects.all()
    #     if self.request.POST:
    #         print(self.request.POST)
    #         return Contract.objects.filter(divisions=int(self.request.POST.get('division')))
    #     return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        context['s'] = f"division={self.request.GET.get('division')}&"
        return context


class ContractAdd(CreateView):
    """
    Создание нового договора
    """
    model = Contract
    form_class = ContractsAddForm
    success_url = reverse_lazy('contracts_app:index')

    def get_context_data(self, **kwargs):
        context = super(ContractAdd, self).get_context_data(**kwargs)
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context

    def post(self, request, *args, **kwargs):
        print(self.get_form(ContractsAddForm))
        return super().post(request, *args, **kwargs)


class ContractDetail(DetailView):
    """
    Просмотр договора.
    """
    model = Contract

    def get_context_data(self, **kwargs):
        context = super(ContractDetail, self).get_context_data(**kwargs)
        # Выбираем из таблицы Posts все записи относящиеся к текущему договору
        post = Posts.objects.filter(contract_number=self.object.pk)
        all_prolongation = Contract.type_of_prolongation
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
        context['prolongation'] = all_prolongation
        return context


class ContractUpdate(UpdateView):
    model = Contract
    form_class = ContractsUpdateForm
    template_name_suffix = '_form_update'

    def post(self, request, *args, **kwargs):

        # print(self.get_form(ContractsAddForm))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            response = form.save(commit=False)
            # print(form)
            response.save()
            return HttpResponseRedirect(reverse('contracts_app:detail', args=[self.object.pk]))
        else:
            print(f'Что то не то')

    def get_context_data(self, **kwargs):
        context = super(ContractUpdate, self).get_context_data(**kwargs)
        all_users = DataBaseUser.objects.all()
        all_type_of_contract = TypeContract.objects.all()
        all_type_property = TypeProperty.objects.all()
        all_counteragent = Counteragent.objects.all()
        all_prolongation = Contract.type_of_prolongation
        all_divisions = Division.objects.all()
        context['employee'] = all_users
        context['type_property'] = all_type_property
        context['counteragent'] = all_counteragent
        context['prolongation'] = all_prolongation
        context['division'] = all_divisions
        context['type_contract'] = all_type_of_contract
        return context

    def get_success_url(self):
        return reverse_lazy('contracts_app:detail', {'pk': self.object.pk})


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
