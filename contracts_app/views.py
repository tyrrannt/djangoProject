import functools
from os import path

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, QueryDict
from django.shortcuts import render, HttpResponseRedirect, get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView, DeleteView
from django.views.generic.detail import SingleObjectMixin

from administration_app.models import PortalProperty
from contracts_app.models import Contract, Posts, TypeContract, TypeProperty
from contracts_app.forms import ContractsAddForm, ContractsPostAddForm, ContractsUpdateForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test
import hashlib

# Create your views here.
from customers_app.models import DataBaseUser


class ContractList(LoginRequiredMixin, ListView):
    """
    Отображение списка договоров
    """
    model = Contract
    paginate_by = 5
    item_sorted = 'pk'
    sorted_list = ['pk', 'contract_counteragent', 'contract_number', 'date_conclusion',
                   'type_of_contract', 'divisions']

    def get_context_data(self, **kwargs):
        context = super(ContractList, self).get_context_data(**kwargs)
        context['title'] = 'База договоров'
        try:
            context['portal_paginator'] = int(self.request.session['portal_paginator'])
            context['sort_item'] = int(self.request.session['sort_item'])
        except Exception as _ex:
            context['portal_paginator'] = self.paginate_by
            context['sort_item'] = 0
        return context

    def get_queryset(self):
        user_access = DataBaseUser.objects.get(pk=self.request.user.pk)
        try:
            if self.request.session['portal_paginator']:
                self.paginate_by = int(self.request.session['portal_paginator'])
            else:
                self.paginate_by = PortalProperty.objects.get(pk=1).portal_paginator

        except Exception as _ex:
            self.paginate_by = PortalProperty.objects.get(pk=1).portal_paginator
        try:
            if self.request.session['sort_item']:
                self.item_sorted = self.sorted_list[int(self.request.session['sort_item'])]
            else:
                self.item_sorted = 'pk'
        except Exception as _ex:
            self.item_sorted = 'pk'
        return Contract.objects.filter(allowed_placed=True).order_by(self.item_sorted)

    def get(self, request, *args, **kwargs):
        result = request.GET.get('result', None)
        sort_item = request.GET.get('sort_item', None)
        if sort_item:
            self.request.session['sort_item'] = sort_item
        if result:
            self.request.session['portal_paginator'] = result

        return super(ContractList, self).get(self, request, *args, **kwargs)


class ContractSearch(LoginRequiredMixin, ListView):
    """
    Поиск договоров в базе
    """
    template_name_suffix = '_search'
    context_object_name = 'object'
    object_list = None
    paginate_by = 5

    def post(self, request):  # ***** this method required! ******
        self.object_list = self.get_queryset()
        return HttpResponseRedirect(reverse('contracts_app:search'))

    # Работает с GET запросом
    def get_queryset(self):
        qs = Contract.objects.all()
        if self.request.GET:
            # ToDo: Вставить валидацию параметров запроса
            dv = int(self.request.GET.get('dv'))
            ca = int(self.request.GET.get('ca'))
            tc = int(self.request.GET.get('tc'))
            tp = int(self.request.GET.get('tp'))
            cn = self.request.GET.get('cn')
            sn = self.request.GET.get('sn')

            """Формируем запрос на лету, в зависимости от полученных параметров, создаем Q объект,
               и добавляем к нему запросы, в зависимости от значений передаваемых параметров.
            """
            query = Q()
            if dv != 0:
                query &= Q(divisions=dv)
            if ca != 0:
                query &= Q(contract_counteragent=ca)
            if tc != 0:
                query &= Q(type_of_contract=tc)
            if tp != 0:
                query &= Q(type_property=tp)
            if cn:
                query &= Q(contract_number__contains=cn)
            if sn:
                query &= Q(subject_contract__contains=sn)
            # query &= Q(access__pk__gte=self.request.user.access_right.pk)
            return Contract.objects.filter(query).order_by('pk')
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
        context = super().get_context_data(**kwargs)

        context['s'] = f"dv={self.request.GET.get('dv')}&ca={self.request.GET.get('ca')}" \
                       f"&tc={self.request.GET.get('tc')}&tp={self.request.GET.get('tp')}" \
                       f"&cn={self.request.GET.get('cn')}&sn={self.request.GET.get('sn')}&"
        context['title'] = 'Поиск по базе договоров'
        return context


class ContractAdd(LoginRequiredMixin, CreateView):
    """
    Создание нового договора
    """
    model = Contract
    form_class = ContractsAddForm
    success_url = reverse_lazy('contracts_app:index')

    def post(self, request, *args, **kwargs):
        # Сохраняем QueryDict в переменную content для возможности его редактирования
        content = QueryDict.copy(self.request.POST)
        # Проверяем на корректность ввода головного документа, если головной документ не указан, то вырезаем его
        if content['parent_category'] == '0':
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
        context['title'] = 'Создание нового договора'
        return context

    def get(self, request, *args, **kwargs):
        """
        Проверка прав доступа к созданию записи в таблице. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.contracts_access_add:
                get_parameters = self.request.GET.get('parent')
                if get_parameters:
                    object_item = Contract.objects.get(pk=get_parameters)
                    context = {'parameter1': object_item.contract_counteragent,
                               'parameter2': object_item}
                    return render(request, 'contracts_app/contract_form.html', context)

                return super(ContractAdd, self).get(request, *args, **kwargs)

            else:
                url_match = reverse_lazy('contracts_app:index')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('contracts_app:index')
            return redirect(url_match)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class ContractDetail(LoginRequiredMixin, DetailView):
    """
    Просмотр договора.
    """
    model = Contract

    def dispatch(self, request, *args, **kwargs):
        try:
            detail_obj = int(self.get_object().access.level)
            user_obj = int(self.request.user.access_level.contracts_access_view)

            if detail_obj < user_obj:
                url_match = reverse_lazy('contracts_app:index')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('contracts_app:index')
            return redirect(url_match)
        return super(ContractDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(ContractDetail, self).get_context_data(**kwargs)
        # if context.get('contract').access.level < int(self.request.user.access_level.contracts_access_view):
        # print(context.get('contract').pk)
        # Выбираем из таблицы Posts все записи относящиеся к текущему договору
        post = Posts.objects.filter(contract_number=self.object.pk)
        slaves = Contract.objects.filter(Q(parent_category=self.object.pk),
                                         Q(access__pk__gte=self.request.user.access_right.pk))
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


class ContractUpdate(LoginRequiredMixin, UpdateView):
    model = Contract
    form_class = ContractsUpdateForm
    template_name_suffix = '_form_update'

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
        """
        Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.contracts_access_edit:
                return super(ContractUpdate, self).get(request, *args, **kwargs)
            else:
                url_match = reverse_lazy('contracts_app:index')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('contracts_app:index')
            return redirect(url_match)

    def get_context_data(self, **kwargs):

        context = super(ContractUpdate, self).get_context_data(**kwargs)
        # Формируем заголовок страницы и передаем в контекст
        if self.object.contract_number:
            cn = self.object.contract_number
        else:
            cn = '(без номера)'
        context['title'] = title = 'Редактирование договора №' + cn + ' от ' + str(self.object.date_conclusion)
        return context

    def get_success_url(self):
        return reverse_lazy('contracts_app:detail', {'pk': self.object.pk})

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class ContractPostAdd(LoginRequiredMixin, CreateView):
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


class ContractPostList(LoginRequiredMixin, ListView):
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


class ContractPostDelete(LoginRequiredMixin, DeleteView):
    """
    Удаление записи
    """
    model = Posts
