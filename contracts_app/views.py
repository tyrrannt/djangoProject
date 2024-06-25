from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import QueryDict, JsonResponse
from django.shortcuts import HttpResponseRedirect, render
from django.views.generic import DetailView, UpdateView, ListView, CreateView, DeleteView
from loguru import logger
from dadata import Dadata
from administration_app.models import PortalProperty
from administration_app.utils import int_validate, change_session_queryset, change_session_context, ajax_search
from contracts_app.models import Contract, Posts, TypeContract, TypeProperty, TypeDocuments, Estate
from contracts_app.forms import ContractsAddForm, ContractsPostAddForm, ContractsUpdateForm, TypeDocumentsUpdateForm, \
    TypeDocumentsAddForm, TypeContractsAddForm, TypeContractsUpdateForm, TypePropertysUpdateForm, TypePropertysAddForm, \
    EstateAddForm, EstateUpdateForm
from django.urls import reverse, reverse_lazy

from customers_app.models import DataBaseUser, Counteragent, CounteragentDocuments


# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


class ContractList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Отображение списка договоров
    """
    model = Contract
    permission_required = 'contracts_app.view_contract'

    def get_context_data(self, **kwargs):
        context = super(ContractList, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // База договоров'
        return context

    def get_queryset(self):
        access = self.request.user.user_access
        return Contract.objects.filter(Q(allowed_placed=True) & Q(access_id__gte=access))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        # if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        #     contract_list = Contract.objects.filter(type_of_document__type_document='Договор').order_by('pk').reverse()
        #     data = [contract_item.get_data() for contract_item in contract_list]
        #     response = {'data': data}
        #     # report_card_separator()
        #     return JsonResponse(response)
        # return super().get(request, *args, **kwargs)
        access = self.request.user.user_access
        query = Q(type_of_document__type_document='Договор') & Q(access_id__gte=access)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['actuality', 'contract_number', 'date_conclusion',
                           'type_of_contract__type_contract', 'subject_contract',
                           'contract_counteragent__short_name', ]
            context = ajax_search(request, self, search_list, Contract, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)


class ContractListAdmin(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Отображение списка договоров
    """
    model = Contract
    template_name = 'contracts_app/contract_list_admin.html'
    permission_required = 'contracts_app.view_contract'

    def get_context_data(self, **kwargs):
        context = super(ContractListAdmin, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // База договоров'
        return context

    def get_queryset(self):
        access = self.request.user.user_access
        return Contract.objects.filter(
            Q(allowed_placed=True) &
            Q(access_id__gte=access) &
            ~Q(doc_file__endswith='.pdf')
        )

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        # if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        #     contract_list = Contract.objects.filter(type_of_document__type_document='Договор').order_by('pk').reverse()
        #     data = [contract_item.get_data() for contract_item in contract_list]
        #     response = {'data': data}
        #     # report_card_separator()
        #     return JsonResponse(response)
        # return super().get(request, *args, **kwargs)
        access = self.request.user.user_access
        query = Q(type_of_document__type_document='Договор') & Q(access_id__gte=access) & ~Q(doc_file__endswith='.pdf')
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['contract_number', 'date_conclusion',
                           'type_of_contract__type_contract', 'subject_contract',
                           'contract_counteragent__short_name', ]
            context = ajax_search(request, self, search_list, Contract, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)


class ContractSearch(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    """
    Поиск договоров в базе
    ToDo: Не работает пагинация при прямом открытии списка. Разобраться почему!!! После нажатия кнопки поиска, все норм.
    """
    template_name_suffix = '_search'
    context_object_name = 'object'
    object_list = None
    paginate_by = 6
    permission_required = 'contracts_app.view_contract'

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


class ContractAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Создание нового договора
    """
    model = Contract
    form_class = ContractsAddForm
    # success_url = reverse_lazy('contracts_app:index')
    permission_required = 'contracts_app.add_contract'

    def form_valid(self, form):
        # Сохраняем QueryDict в переменную content для возможности его редактирования
        # content = QueryDict.copy(self.request.POST)
        # Проверяем на корректность ввода головного документа, если головной документ не указан, то вырезаем его
        # if content['parent_category'] == 'none':
        #     content.setlist('parent_category', '')
        # Проверяем подразделения, если пришел список с 0 значением, то удаляем его
        refreshed_form = form.save(commit=False)
        if refreshed_form.parent_category:
             refreshed_form.official_information = refreshed_form.doc_file

        refreshed_form.save()

        return super().form_valid(form)


    def get_success_url(self):
        obj = self.object
        if obj.parent_category:
            return reverse('contracts_app:detail', kwargs={'pk': obj.parent_category.pk})
        else:
            return reverse('contracts_app:index')

    def post(self, request, *args, **kwargs):
        # Сохраняем QueryDict в переменную content для возможности его редактирования
        content = QueryDict.copy(self.request.POST)
        if content['parent_category'] == content['contract_counteragent']:
            print(content['parent_category'], content['contract_counteragent'])
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
        return context

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        parent = self.request.GET.get('parent', None)
        kwargs = super().get_form_kwargs()
        kwargs.update({'parent': parent})
        kwargs.update({'executor': self.request.user.pk})
        return kwargs

    def get(self, request, *args, **kwargs):

        return super(ContractAdd, self).get(request, *args, **kwargs)


class ContractDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Просмотр договора.
    """
    model = Contract
    permission_required = 'contracts_app.view_contract'

    def dispatch(self, request, *args, **kwargs):
        try:
            contract_object = self.get_object()
            if request.user.user_access.pk <= contract_object.access.pk or request.user.is_superuser:
                return super(ContractDetail, self).dispatch(request, *args, **kwargs)
            else:
                logger.warning(f'Пользователь {request.user} хотел получить доступ к договору {contract_object}')
                raise PermissionDenied
        except PermissionDenied:
            return render(request, "library_app/403.html")

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
        context[
            'title'] = title = f'{PortalProperty.objects.all().last().portal_name} // Просмотр договора №' + cn + ' от ' + str(
            self.object.date_conclusion)
        # Передаем найденные записи в контекст
        if not self.object.parent_category:
            context['not_parent'] = True
        context['posts'] = post
        context['slaves'] = slaves
        context['counteragent_docs'] = CounteragentDocuments.objects.filter(package=self.object.contract_counteragent)
        return context


class ContractUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractsUpdateForm
    template_name = 'contracts_app/contract_form_update.html'
    permission_required = 'contracts_app.change_contract'

    def dispatch(self, request, *args, **kwargs):
        try:
            contract_object = self.get_object()
            if request.user.user_access.pk <= contract_object.access.pk:  # or request.user.is_superuser:
                return super(ContractUpdate, self).dispatch(request, *args, **kwargs)
            else:
                logger.warning(f'Пользователь {request.user} хотел получить доступ к договору {contract_object}')
                raise PermissionDenied
        except PermissionDenied:
            return render(request, "library_app/403.html")

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    # def get_form_kwargs(self):
    #     """
    #     Передаем в форму текущего пользователя. В форме переопределяем метод __init__
    #     :return: PK текущего пользователя
    #     """
    #     kwargs = super().get_form_kwargs()
    #     kwargs.update({"parent": self.object.parent_category})
    #     kwargs.update({"contragent": self.object.contract_counteragent.pk})
    #     return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class=self.form_class)
        # form.fields['contract_counteragent'].queryset = Counteragent.objects.filter(
        #     pk=self.object.contract_counteragent.pk)
        if self.object.parent_category:
            form.fields['parent_category'].queryset = Contract.objects.filter(
                parent_category=self.object.parent_category.pk)
        return form

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
        contragent = request.GET.get("contragent", None)
        print(contragent)
        if contragent:
            print(contragent)
        return super(ContractUpdate, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):

        context = super(ContractUpdate, self).get_context_data(**kwargs)
        # Формируем заголовок страницы и передаем в контекст
        if self.object.contract_number:
            cn = self.object.contract_number
        else:
            cn = '(без номера)'
        context[
            'title'] = title = f'{PortalProperty.objects.all().last().portal_name} // Изменить договор №' + cn + ' от ' + str(
            self.object.date_conclusion)

        return context

    def get_success_url(self):
        return reverse_lazy('contracts_app:detail', {'pk': self.object.pk})

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class ContractPostAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
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


class ContractPostList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
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


class ContractPostDelete(PermissionRequiredMixin, LoginRequiredMixin, DeleteView):
    """
    Удаление записи
    """
    model = Posts
    permission_required = 'hrdepartment_app.delete_posts'


"""
Типы документов: Список, Добавление, Детализация, Обновление
"""


class TypeDocumentsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
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


class TypeDocumentsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
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


class TypeDocumentsDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = TypeDocuments
    template_name = 'contracts_app/typedocuments_detail.html'
    permission_required = 'hrdepartment_app.view_typedocuments'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypeDocumentsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
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


class TypeContractsList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
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


class TypeContractsAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
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


class TypeContractsDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = TypeContract
    template_name = 'contracts_app/typecontracts_detail.html'
    permission_required = 'hrdepartment_app.view_typecontract'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypeContractsUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
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


class TypePropertysList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
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


class TypePropertysAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
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


class TypePropertysDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = TypeProperty
    template_name = 'contracts_app/typepropertys_detail.html'
    permission_required = 'hrdepartment_app.view_typeproperty'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class TypePropertysUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
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


"""
Имущества: Список, Добавление, Детализация, Обновление
"""


class EstateList(PermissionRequiredMixin, LoginRequiredMixin, ListView):
    model = Estate
    permission_required = 'hrdepartment_app.view_estate'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            type_property_list = Estate.objects.all()
            data = [type_property_item.get_data() for type_property_item in type_property_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Имущества'
        return context


class EstateAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = Estate
    form_class = EstateAddForm
    permission_required = 'hrdepartment_app.add_estate'

    def get(self, request, *args, **kwargs):
        return super(EstateAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:estate_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить имущества'
        return context


class EstateDetail(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = Estate
    permission_required = 'hrdepartment_app.view_estate'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Просмотр - {self.get_object()}'
        return context


class EstateUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Estate
    form_class = EstateUpdateForm
    permission_required = 'hrdepartment_app.change_estate'

    def get(self, request, *args, **kwargs):
        return super(EstateUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('contracts_app:estate_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование - {self.get_object()}'
        return context


def counteragent_check(request):
    if request.method == 'POST':
        data = request.POST
        if data.get('counteragent') == '' and data.get('counteragent_name') == '':
            return HttpResponseRedirect(reverse('contracts_app:counteragent_check'))
        else:
            token = config('FNS')
            ddata = Dadata(token)
            inn = str(data.get('counteragent'))
            kpp = str(data.get('counteragent_kpp'))
            name = str(data.get('counteragent_name')).strip()
            if kpp:
                res = ddata.find_by_id("party", inn, kpp=kpp)
            else:
                if inn:
                    res = ddata.find_by_id("party", inn)
                else:
                    res = ddata.suggest("party", name)

            data = {'query': res}
            return render(request, 'contracts_app/counteragent_check.html', context=data)
    else:
        return render(request, 'contracts_app/counteragent_check.html')
