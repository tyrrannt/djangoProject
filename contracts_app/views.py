import pathlib
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import QueryDict, JsonResponse
from django.shortcuts import HttpResponseRedirect, redirect
from django.views.generic import DetailView, UpdateView, ListView, CreateView, DeleteView

from administration_app.models import PortalProperty
from administration_app.utils import int_validate, change_session_get, change_session_queryset, change_session_context
from contracts_app.models import Contract, Posts, TypeContract, TypeProperty, TypeDocuments
from contracts_app.forms import ContractsAddForm, ContractsPostAddForm, ContractsUpdateForm, TypeDocumentsUpdateForm, \
    TypeDocumentsAddForm, TypeContractsAddForm, TypeContractsUpdateForm, TypePropertysUpdateForm, TypePropertysAddForm
from django.urls import reverse, reverse_lazy

from customers_app.models import DataBaseUser, Counteragent
from djangoProject import settings


class ContractList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Отображение списка договоров
    """
    model = Contract
    paginate_by = 6
    item_sorted = 'pk'
    sorted_list = ['pk', 'contract_counteragent', 'contract_number', 'date_conclusion',
                   'type_of_contract', 'divisions']
    permission_required = 'hrdepartment_app.view_contract'

    def get_context_data(self, **kwargs):
        context = super(ContractList, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // База договоров'
        change_session_context(context, self)
        return context

    def get_queryset(self):
        change_session_queryset(self.request, self)
        return Contract.objects.filter(Q(allowed_placed=True)).order_by(self.item_sorted)

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            contract_list = Contract.objects.all().order_by('pk').reverse()
            data = [contract_item.get_data() for contract_item in contract_list]
            response = {'data': data}
            # report_card_separator()
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class ContractSearch(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Поиск договоров в базе
    ToDo: Не работает пагинация при прямом открытии списка. Разобраться почему!!! После нажатия кнопки поиска, все норм.
    """
    template_name_suffix = '_search'
    context_object_name = 'object'
    object_list = None
    paginate_by = 6
    permission_required = 'hrdepartment_app.view_contract'

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('contracts_app:search'))

    # Работает с GET запросом
    def get_queryset(self):
        query = Q()
        query &= Q(allowed_placed=True)
        # query &= Q(access__pk__gte=DataBaseUser.objects.get(
        #     pk=self.request.user.pk).access_level.contracts_access_view.level)
        qs = Contract.objects.filter(query).order_by('pk')
        if self.request.GET:
            dv = self.request.GET.get('dv')
            ca = self.request.GET.get('ca')
            tc = self.request.GET.get('tc')
            tp = self.request.GET.get('tp')
            cn = self.request.GET.get('cn')
            sn = self.request.GET.get('sn')
            """Формируем запрос на лету, в зависимости от полученных параметров, создаем Q объект,
               и добавляем к нему запросы, в зависимости от значений передаваемых параметров.
            """
            if dv != '0':
                query &= Q(divisions=int_validate(dv))
            if ca != '0':
                query &= Q(contract_counteragent=int_validate(ca))
            if tc != '0':
                query &= Q(type_of_contract=int_validate(tc))
            if tp != '0':
                query &= Q(type_property=int_validate(tp))
            if cn:
                query &= Q(contract_number__contains=cn)
            if sn:
                query &= Q(subject_contract__contains=sn)
            qs = Contract.objects.filter(query).order_by('pk')
        return qs

    ##ToDo: Доработать передачу поискового запроса через POST
    ## Работает с POST запросом
    # def get_queryset(self):
    #     qs = Contract.objects.all()
    #     if self.request.POST:
    #         print(self.request.POST)
    #         return Contract.objects.filter(divisions=int(self.request.POST.get('division')))
    #     return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        # Формируем строку GET запроса при пагинации
        get_request_string = f"dv={self.request.GET.get('dv')}&ca={self.request.GET.get('ca')}" \
                             f"&tc={self.request.GET.get('tc')}&tp={self.request.GET.get('tp')}" \
                             f"&cn={self.request.GET.get('cn')}&sn={self.request.GET.get('sn')}&"
        if get_request_string == 'dv=None&ca=None&tc=None&tp=None&cn=None&sn=None&':
            context['s'] = ''
        else:
            context['s'] = get_request_string

        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Поиск по базе договоров'
        return context


class ContractAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Создание нового договора
    """
    model = Contract
    form_class = ContractsAddForm
    success_url = reverse_lazy('contracts_app:index')
    permission_required = 'hrdepartment_app.add_contract'

    def post(self, request, *args, **kwargs):
        # Сохраняем QueryDict в переменную content для возможности его редактирования
        content = QueryDict.copy(self.request.POST)
        if content['parent_category'] == content['contract_counteragent']:
            self.form_invalid()
        # Проверяем на корректность ввода головного документа, если головной документ не указан, то вырезаем его
        if content['parent_category'] == 'none':
            content.setlist('parent_category', '')
        # Проверяем подразделения, если пришел список с 0 значением, то удаляем его из списка, генерируя новый список
        division = list(k for k in content.getlist('divisions') if k != '0')
        type_propertyes = list(k for k in content.getlist('type_property') if k != '0')
        content.setlist('divisions', division)
        content.setlist('type_property', type_propertyes)
        # Возвращаем измененный QueryDict обратно в запрос
        self.request.POST = content
        return super(ContractAdd, self).post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ContractAdd, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить новый договор'
        context['all_contract'] = Contract.objects.all()
        context['all_counteragent'] = Counteragent.objects.all()
        return context

    def get(self, request, *args, **kwargs):
        return super(ContractAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        files = self.request.FILES.getlist('doc_file')
        for item in files:
            paths = default_storage.save(pathlib.Path.joinpath(settings.MEDIA_URL, 'hr'), ContentFile(item.read()))
            print("images path are", paths)
        form.clean()
        return super(ContractAdd, self).form_valid(form)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class ContractDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """
    Просмотр договора.
    """
    model = Contract
    permission_required = 'hrdepartment_app.view_contract'

    def dispatch(self, request, *args, **kwargs):
        return super(ContractDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ContractDetail, self).get_context_data(**kwargs)
        # if context.get('contract').access.level < int(self.request.user.access_level.contracts_access_view):
        # print(context.get('contract').pk)
        # Выбираем из таблицы Posts все записи относящиеся к текущему договору
        post = Posts.objects.filter(contract_number=self.object.pk)
        slaves = Contract.objects.filter(Q(parent_category=self.object.pk))
        # Формируем заголовок страницы и передаем в контекст
        if self.object.contract_number:
            cn = self.object.contract_number
        else:
            cn = '(без номера)'
        context['title'] = title = f'{PortalProperty.objects.all().last().portal_name} // Просмотр договора №' + cn + ' от ' + str(self.object.date_conclusion)
        # Передаем найденные записи в контекст
        context['posts'] = post
        context['slaves'] = slaves
        return context


class ContractUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractsUpdateForm
    template_name_suffix = '_form_update'
    permission_required = 'hrdepartment_app.change_contract'

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Проверяем корректность переданной формы
        :param form: Передаваемая форма с сайта
        :return: Редирект обратно на страницу с обновленными данными
        """

        if form.is_valid():
            # в old_instance сохраняем старые значения записи
            old_instance = Contract.objects.get(pk=self.object.pk).__dict__
            form.save()
            # в new_instance сохраняем новые значения записи
            new_instance = Contract.objects.get(pk=self.object.pk).__dict__
            # создаем генератор списка
            diffkeys = [k for k in old_instance if old_instance[k] != new_instance[k]]
            message = '<b>Запись внесена автоматически!</b> <u>Внесены изменения</u>:\n'
            for k in diffkeys:
                if k != '_state':
                    message += f'{Contract._meta.get_field(k).verbose_name}: <strike>{old_instance[k]}</strike> -> {new_instance[k]}\n'
            post_record = Posts(contract_number=Contract.objects.get(pk=self.object.pk), post_description=message,
                                responsible_person=DataBaseUser.objects.get(pk=self.request.user.pk))
            post_record.save()
            return HttpResponseRedirect(reverse('contracts_app:detail', args=[self.object.pk]))
        else:
            print(f'Что то не то')

    def get(self, request, *args, **kwargs):
        # """
        # Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        # """
        # pk = int(self.request.user.pk)
        # try:
        #     if DataBaseUser.objects.get(pk=pk).access_level.contracts_access_edit:
        #         return super(ContractUpdate, self).get(request, *args, **kwargs)
        #     else:
        #         url_match = reverse_lazy('contracts_app:index')
        #         return redirect(url_match)
        # except Exception as _ex:
        #     url_match = reverse_lazy('contracts_app:index')
        #     return redirect(url_match)
        return super(ContractUpdate, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):

        context = super(ContractUpdate, self).get_context_data(**kwargs)
        # Формируем заголовок страницы и передаем в контекст
        if self.object.contract_number:
            cn = self.object.contract_number
        else:
            cn = '(без номера)'
        context['title'] = title = f'{PortalProperty.objects.all().last().portal_name} // Изменить договор №' + cn + ' от ' + str(self.object.date_conclusion)

        return context

    def get_success_url(self):
        return reverse_lazy('contracts_app:detail', {'pk': self.object.pk})

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class ContractPostAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Добавление записи к договору.
    """
    model = Posts
    form_class = ContractsPostAddForm
    permission_required = 'hrdepartment_app.add_posts'

    def get_success_url(self):
        """
        Переопределяется метод 'get_success_url', для получения номера договора 'pk',
        к которому добавляется запись, для того чтоб вернуться на страницу договора
        :return: Возвращается URL на договор
        """
        pk = self.object.contract_number.pk
        return reverse("contracts_app:detail", kwargs={"pk": pk})


class ContractPostList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Вывод списка записей, относящихся к конкретному договору
    """
    model = Posts
    permission_required = 'hrdepartment_app.view_posts'

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


class ContractPostDelete(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """
    Удаление записи
    """
    model = Posts
    permission_required = 'hrdepartment_app.delete_posts'


"""
Типы документов: Список, Добавление, Детализация, Обновление
"""


class TypeDocumentsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TypeDocuments
    template_name = 'contracts_app/typedocuments_list.html'
    permission_required = 'hrdepartment_app.view_typedocuments'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            type_documents_list = TypeDocuments.objects.all()
            data = [type_documents_item.get_data() for type_documents_item in type_documents_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Типы документов'
        return context


class TypeDocumentsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TypeDocuments
    form_class = TypeDocumentsAddForm
    template_name = 'contracts_app/typedocuments_add.html'
    permission_required = 'hrdepartment_app.add_typedocuments'

    def get(self, request, *args, **kwargs):
        return super(TypeDocumentsAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typedocuments_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить тип документа'
        return context


class TypeDocumentsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = TypeDocuments
    template_name = 'contracts_app/typedocuments_detail.html'
    permission_required = 'hrdepartment_app.view_typedocuments'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypeDocumentsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TypeDocuments
    template_name = 'contracts_app/typedocuments_update.html'
    form_class = TypeDocumentsUpdateForm
    permission_required = 'hrdepartment_app.change_typedocuments'

    def get(self, request, *args, **kwargs):
        return super(TypeDocumentsUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typedocuments', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


"""
Типы договоров: Список, Добавление, Детализация, Обновление
"""


class TypeContractsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TypeContract
    template_name = 'contracts_app/typecontracts_list.html'
    permission_required = 'hrdepartment_app.view_typecontract'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            type_contracts_list = TypeContract.objects.all()
            data = [type_contracts_item.get_data() for type_contracts_item in type_contracts_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Типы договоров'
        return context


class TypeContractsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TypeContract
    form_class = TypeContractsAddForm
    template_name = 'contracts_app/typecontracts_add.html'
    permission_required = 'hrdepartment_app.add_typecontract'

    def get(self, request, *args, **kwargs):
        return super(TypeContractsAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typecontracts_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить тип договора'
        return context


class TypeContractsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = TypeContract
    template_name = 'contracts_app/typecontracts_detail.html'
    permission_required = 'hrdepartment_app.view_typecontract'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypeContractsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TypeContract
    template_name = 'contracts_app/typecontracts_update.html'
    form_class = TypeContractsUpdateForm
    permission_required = 'hrdepartment_app.change_typecontract'

    def get(self, request, *args, **kwargs):
        return super(TypeContractsUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typecontracts', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


"""
Типы имущества: Список, Добавление, Детализация, Обновление
"""


class TypePropertysList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TypeProperty
    template_name = 'contracts_app/typepropertys_list.html'
    permission_required = 'hrdepartment_app.view_typeproperty'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            type_property_list = TypeProperty.objects.all()
            data = [type_property_item.get_data() for type_property_item in type_property_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Типы имущества'
        return context


class TypePropertysAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TypeProperty
    form_class = TypePropertysAddForm
    template_name = 'contracts_app/typepropertys_add.html'
    permission_required = 'hrdepartment_app.add_typeproperty'

    def get(self, request, *args, **kwargs):
        return super(TypePropertysAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typepropertys_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить тип имущества'
        return context


class TypePropertysDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = TypeProperty
    template_name = 'contracts_app/typepropertys_detail.html'
    permission_required = 'hrdepartment_app.view_typeproperty'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypePropertysUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TypeProperty
    template_name = 'contracts_app/typepropertys_update.html'
    form_class = TypePropertysUpdateForm
    permission_required = 'hrdepartment_app.change_typeproperty'

    def get(self, request, *args, **kwargs):
        return super(TypePropertysUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:typepropertys', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context
