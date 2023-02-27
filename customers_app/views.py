import datetime
from loguru import logger
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, CreateView, ListView

from administration_app.models import PortalProperty
from administration_app.utils import boolean_return, get_jsons_data, transliterate, get_jsons_data_filter, \
    change_session_get, change_session_queryset, change_session_context, get_jsons
from contracts_app.models import TypeDocuments, Contract
from customers_app.customers_util import get_database_user_profile
from customers_app.models import DataBaseUser, Posts, Counteragent, UserAccessMode, Division, Job, AccessLevel, \
    DataBaseUserWorkProfile, Citizenships, IdentityDocuments, HarmfulWorkingConditions
from customers_app.models import DataBaseUserProfile as UserProfile
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm, PostsAddForm, \
    CounteragentUpdateForm, StaffUpdateForm, DivisionsAddForm, DivisionsUpdateForm, JobsAddForm, JobsUpdateForm, \
    CounteragentAddForm, PostsUpdateForm
from django.contrib import auth
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

# Create your views here.
from hrdepartment_app.models import OfficialMemo, ApprovalOficialMemoProcess

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip", serialize=True)

def get_model_fields(model_object):
    return model_object._meta.fields

@logger.catch
def get_profile_fill(self, context):
    profile_info = 0
    user_object = self.get_object()
    user_private = user_object.user_profile
    user_work = user_object.user_work_profile
    user_object_list = ['first_name', 'last_name', 'email', 'surname', 'avatar', 'birthday', 'address',
                        'personal_phone', 'gender']
    user_private_list = ['citizenship', 'passport', 'snils', 'oms', 'inn']
    user_work_list = ['date_of_employment', 'internal_phone', 'work_phone', 'job', 'divisions', 'work_email']
    for item in get_model_fields(user_object):
        if str(item).split('.')[2] in user_object_list:
            if getattr(user_object, str(item).split('.')[2]):
                profile_info += 5
    try:
        for item in get_model_fields(user_private):
            if str(item).split('.')[2] in user_private_list:
                if getattr(user_private, str(item).split('.')[2]):
                    profile_info += 5
    except Exception as _ex:
        print(f'{_ex}: Отсутствует блок личной информации')
    try:
        for item in get_model_fields(user_work):
            if str(item).split('.')[2] in user_work_list:
                if getattr(user_work, str(item).split('.')[2]):
                    profile_info += 5
    except Exception as _ex:
        print(f'{_ex}: Отсутствует блок рабочей информации')
    context['profile_info'] = profile_info


@login_required
def index(request):
    document_types = TypeDocuments.objects.all()
    category = list()
    for item in document_types:
        category.append(item.type_document)
    values = list()
    for item in document_types:
        values.append(Contract.objects.filter(type_of_document=item).count())
    types_count = dict(zip(category, values))
    return render(request, 'customers_app/customers.html', context={'types_count': types_count})


class DataBaseUserProfileDetail(LoginRequiredMixin, DetailView):
    context = {}
    model = DataBaseUser
    template_name = 'customers_app/user_profile.html'

    @method_decorator(user_passes_test(lambda u: u.is_active))
    def dispatch(self, request, *args, **kwargs):
        return super(DataBaseUserProfileDetail, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserProfileDetail, self).get_context_data(**kwargs)
        user_obj = self.get_object()#DataBaseUser.objects.get(pk=self.request.user.pk)
        print(user_obj)

        try:
            post_high = Posts.objects.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                             Q(post_date_start__gt=datetime.datetime.today())).order_by(
                '-post_date_start')
            post_low = Posts.objects.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                            Q(post_date_start__lte=datetime.datetime.today())).order_by(
                '-post_date_start')
            context['post_high'] = post_high
            context['post_low'] = post_low
        except Exception as _ex:
            print(user_obj)
            message = f'{user_obj}, У пользователя отсутствует подразделение!!!: {_ex}'
            logger.debug(message)
        context['title'] = 'редактирование'
        context['sp'] = OfficialMemo.objects.all().count()
        context['bp'] = ApprovalOficialMemoProcess.objects.all().count()
        context['contract'] = Contract.objects.all().count()
        get_profile_fill(self, context)

        # context.update(groups())
        return context


class DataBaseUserUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    template_name = 'customers_app/user_profile_update.html'
    form_class = DataBaseUserUpdateForm

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserUpdate, self).get_context_data(**kwargs)
        user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
        try:
            post = Posts.objects.filter(post_divisions__pk=user_obj.user_work_profile.divisions.pk).order_by(
            'creation_date').reverse()
            context['posts'] = post
        except Exception as _ex:
            message = f'{user_obj}, Ошибка получения записей. У пользователя |{user_obj.username}| отсутствует подразделение!!!: {_ex}'
            logger.error(message)

        context['title'] = 'Профиль пользователя'

        context['sp'] = OfficialMemo.objects.all().count()
        context['bp'] = ApprovalOficialMemoProcess.objects.all().count()
        context['contract'] = Contract.objects.all().count()
        get_profile_fill(self, context)
        return context

    def get_success_url(self):
        pk = self.request.user.pk
        return reverse("customers_app:profile", kwargs={"pk": pk})

    def get(self, request, *args, **kwargs):
        """
        Проверка пользователя, при попытке отредактировать профиль другого пользователя путем подстановки в адресной
        строке чужого ID, будет произведено перенаправление пользователя на свою страницу с профилем.
        :param request: Передаваемый запрос
        :param kwargs: Получаем передаваемый ID пользователя из строки в браузере
        :return: В случае подмены ID выполняет редирект 302
        """
        if self.request.user.pk != self.kwargs['pk']:
            url_match = reverse('customers_app:profile', kwargs={"pk": self.request.user.pk})
            return redirect(url_match)
        return super(DataBaseUserUpdate, self).get(request, *args, **kwargs)


def login(request):
    content = {'title': 'вход'}
    login_form = DataBaseUserLoginForm(data=request.POST)
    content['login_form'] = login_form
    if request.method == 'POST' and login_form.is_valid():
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(username=username, password=password)
        portal = PortalProperty.objects.all()
        if user and user.is_active:
            auth.login(request, user)
            try:
                portal_session = portal.first().portal_session
            except Exception as _ex:
                portal_session = 900
                print(f'{_ex}: Не заданы базовые параметры длительности сессии пользователя')
            try:
                portal_paginator = portal.first().portal_paginator
            except Exception as _ex:
                portal_paginator = 900
                print(f'{_ex}: Не заданы базовые параметры пагинации страниц')
            request.session.set_expiry(portal_session)
            request.session['portal_paginator'] = portal_paginator
            # return HttpResponseRedirect(reverse('customers_app:index'))  # , args=(user,))
            return HttpResponseRedirect(reverse_lazy('customers_app:profile', args=(user.pk,)))  # , args=(user,))
    # else:
    #     content['errors'] = login_form.get_invalid_login_error()
    return render(request, 'customers_app/login.html', content)


def logout(request):
    auth.logout(request)
    return HttpResponseRedirect(reverse('customers_app:login'))


class SignUpView(CreateView):
    template_name = 'customers_app/register.html'
    form_class = DataBaseUserRegisterForm
    model = DataBaseUser
    success_url = reverse_lazy('customers_app:login')

    def form_valid(self, form):
        valid = super().form_valid(form)
        login(self.request)
        return valid


def validate_username(request):
    """Проверка доступности логина"""
    username = request.GET.get('username', None)
    response = {
        'is_taken': DataBaseUser.objects.filter(username__iexact=username).exists()
    }
    return JsonResponse(response)


class PostsAddView(LoginRequiredMixin, CreateView):
    template_name = 'customers_app/posts_add.html'
    form_class = PostsAddForm
    model = Posts

    def get_context_data(self, **kwargs):
        context = super(PostsAddView, self).get_context_data()
        context['users'] = DataBaseUser.objects.get(pk=self.request.user.pk)
        return context

    def get_success_url(self):
        """
        Получение URL при удачном добавлении нового сообщения. Получаем ID пользователя из request, и передача его
        в качестве параметра
        :return: Возвращает URL адрес страницы, с которой создавалось сообщение.
        """
        pk = self.request.user.pk
        return reverse("customers_app:profile", kwargs={"pk": pk})


class PostsListView(LoginRequiredMixin, ListView):
    template_name = 'customers_app/posts_list.html'
    model = Posts
    paginate_by = 6

    def get_queryset(self):
        user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
        qs = Posts.objects.filter(post_divisions__pk=user_obj.user_work_profile.divisions.pk).order_by('pk').reverse()
        return qs


class PostsDetailView(LoginRequiredMixin, DetailView):
    template_name = 'customers_app/posts_detail.html'
    model = Posts


class PostsUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'customers_app/posts_detail_update.html'
    model = Posts
    form_class = PostsUpdateForm

    def get_success_url(self):
        """
               Получение URL при удачном добавлении нового сообщения. Получаем ID пользователя из request, и передача
               его в качестве параметра
               :return: Возвращает URL адрес страницы, с которой создавалось сообщение.
               """
        pk = self.request.user.pk
        return reverse("customers_app:post_list")


class CounteragentListView(LoginRequiredMixin, ListView):
    # template_name = 'customers_app/counteragent_list.html'  # Совпадает с именем по умолчании
    model = Counteragent
    paginate_by = 6

    def get_queryset(self):
        qs = Counteragent.objects.all().order_by('pk')
        change_session_queryset(self.request, self)
        return qs

    def get(self, request, *args, **kwargs):
        count = 0
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "Контрагенты", 1)
            # ToDo: Счетчик добавленных контрагентов из 1С. Подумать как передать его значение
            for item in todos['value']:
                if not item['IsFolder']:
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'short_name': item['Description'],
                        'full_name': item['НаименованиеПолное'],
                        'inn': item['ИНН'],
                        'kpp': item['КПП'],
                        'ogrn': item['РегистрационныйНомер'],
                        'base_counteragent': False,
                    }
                    Counteragent.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**divisions_kwargs})
                    count += 1
            url_match = reverse_lazy('customers_app:counteragent_list')
            return redirect(url_match)
        change_session_get(self.request, self)
        return super(CounteragentListView, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(CounteragentListView, self).get_context_data(**kwargs)
        context['title'] = 'Список контрагентов'
        change_session_context(context, self)
        return context


class CounteragentAdd(LoginRequiredMixin, CreateView):
    model = Counteragent
    form_class = CounteragentAddForm
    template_name = 'customers_app/counteragent_add.html'

    def get_context_data(self, **kwargs):
        context = super(CounteragentAdd, self).get_context_data(**kwargs)
        context['counteragent_users'] = DataBaseUser.objects.all()
        context['type_counteragent'] = Counteragent.type_of
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)
        if content['director'] == 'none':
            content.setlist('director', '')
        if content['accountant'] == 'none':
            content.setlist('accountant', '')
        if content['contact_person'] == 'none':
            content.setlist('contact_person', '')
        self.request.POST = content
        return super(CounteragentAdd, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:counteragent_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class CounteragentDetail(LoginRequiredMixin, DetailView):
    # template_name = 'customers_app/counteragent_detail.html'  # Совпадает с именем по умолчании
    model = Counteragent


class CounteragentUpdate(LoginRequiredMixin, UpdateView):
    # template_name = 'customers_app/counteragent_form.html'  # Совпадает с именем по умолчании
    model = Counteragent
    form_class = CounteragentUpdateForm

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа у пользователя к редактированию
            if not DataBaseUser.objects.get(pk=self.request.user.pk).access_level.guide_access_edit:
                # Если права доступа отсутствуют у пользователя, производим перенаправление к списку контрагентов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('customers_app:counteragent_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку контрагентов
            url_match = reverse_lazy('customers_app:counteragent_list')
            return redirect(url_match)
        return super(CounteragentUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(CounteragentUpdate, self).get_context_data(**kwargs)
        context['counteragent_users'] = DataBaseUser.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)
        if content['director'] == 'none':
            content.setlist('director', '')
        if content['accountant'] == 'none':
            content.setlist('accountant', '')
        if content['contact_person'] == 'none':
            content.setlist('contact_person', '')
        self.request.POST = content
        return super(CounteragentUpdate, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:counteragent', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class StaffListView(LoginRequiredMixin, ListView):
    template_name = 'customers_app/staff_list.html'
    model = DataBaseUser
    paginate_by = 6
    item_sorted = 'pk'
    sorted_list = ['pk', 'last_name', 'user_work_profile__divisions__code', 'user_work_profile__job__name']

    def get_context_data(self, **kwargs):
        context = super(StaffListView, self).get_context_data(**kwargs)
        context['title'] = 'Список пользователей'
        change_session_context(context, self)
        return context

    def get_queryset(self):
        change_session_queryset(self.request, self)
        qs = DataBaseUser.objects.all().order_by('pk').exclude(is_superuser=True).order_by(self.item_sorted)
        return qs

    def get(self, request, *args, **kwargs):
        change_session_get(request, self)
        count = 0
        count2 = 0
        count3 = DataBaseUser.objects.all().count() + 1
        if self.request.GET.get('update') == '1':
            users_list = DataBaseUser.objects.all().exclude(is_superuser=True)
            for units in users_list:
                job_code, division_code, date_of_employment = '', '', '1900-01-01'
                todo_str = get_jsons(
                    f"http://192.168.10.11/72095052-970f-11e3-84fb-00e05301b4e4/odata/standard.odata/InformationRegister_КадроваяИсторияСотрудников?$format=application/json;odata=nometadata&$filter=RecordSet/any(d:%20d/Сотрудник_Key%20eq%20guid%27{units.ref_key}%27)")
                period = datetime.datetime.strptime("1900-01-01", "%Y-%m-%d")
                if units.ref_key != "":
                    moving = 0
                    for items in todo_str['value']:
                        for items2 in items['RecordSet']:
                            if items2['Active'] == True and items2['ВидСобытия'] == 'Перемещение':
                                if period < datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d"):
                                    period = datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d")
                                    division_code = items2['Подразделение_Key']
                                    job_code = items2['Должность_Key']
                                    moving = 1

                            if items2['Active'] == True and items2['ВидСобытия'] == 'Прием':
                                date_of_employment = datetime.datetime.strptime(items2['Period'][:10], "%Y-%m-%d")
                                if moving == 0:
                                    division_code = items2['Подразделение_Key']
                                    job_code = items2['Должность_Key']
                    user_work_profile = {
                        # 'ref_key': units.ref_key,
                        'date_of_employment': date_of_employment,
                        'job': Job.objects.get(ref_key=job_code) if job_code not in ["", '00000000-0000-0000-0000-000000000000'] else None,
                        'divisions': Division.objects.get(ref_key=division_code) if division_code not in ["", '00000000-0000-0000-0000-000000000000'] else None,
                    }

                    DataBaseUserWorkProfile.objects.update_or_create(ref_key=units.ref_key, defaults=user_work_profile)

                    if not units.user_work_profile:
                        units.user_work_profile = DataBaseUserWorkProfile.objects.get(ref_key=units.ref_key)
                        units.save()

        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "Сотрудники", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Description'] != "" and item['ВАрхиве'] == False:
                    Ref_Key, username, first_name = '', '', ''
                    personal_kwargs = {}
                    last_name, surname, birthday, gender, email, telephone, address, = '', '', '1900-01-01', '', '', '', '',
                    todos2 = get_jsons_data_filter("Catalog", "ФизическиеЛица", "Ref_Key", item['ФизическоеЛицо_Key'],
                                                   0, 0)
                    for item2 in todos2['value']:
                        Ref_Key = item2['Ref_Key']
                        username = '0' * (4 - len(str(count3))) + str(count3) + '_' + transliterate(
                            item2['Фамилия']).lower() + '_' + \
                                   transliterate(item2['Имя']).lower()[:1] + \
                                   transliterate(item2['Отчество']).lower()[:1]
                        first_name = item2['Имя']
                        last_name = item2['Фамилия']
                        surname = item2['Отчество']
                        gender = 'male' if item2['Пол'] == 'Мужской' else 'female'
                        birthday = datetime.datetime.strptime(item2['ДатаРождения'][:10], "%Y-%m-%d")
                        for item3 in item2['КонтактнаяИнформация']:
                            if item3['Тип'] == 'АдресЭлектроннойПочты':
                                email = item3['АдресЭП']
                            if item3['Тип'] == 'Телефон':
                                telephone = '+' + item3['НомерТелефона']
                            if item3['Тип'] == 'Адрес':
                                address = item3['Представление']
                        personal_kwargs = {
                            #'ref_key': item2['Ref_Key'],
                            'inn': item2['ИНН'],
                            'snils': item2['СтраховойНомерПФР'],
                            'oms': get_database_user_profile(item2['Ref_Key']),
                        }

                    divisions_kwargs = {
                        # 'ref_key': item['Ref_Key'],
                        'person_ref_key': Ref_Key,
                        'service_number': item['Code'],
                        'username': username,
                        'first_name': first_name,
                        'last_name': last_name,
                        'surname': surname,
                        'birthday': birthday,
                        'type_users': 'staff_member',
                        'gender': gender,
                        'email': email,
                        'personal_phone': telephone[:12],
                        'address': address,
                    }
                    count2 += 1
                    count3 += 1
                    try:
                        main_obj_item, main_created = DataBaseUser.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**divisions_kwargs})
                    except Exception as _ex:
                        logger.error(f'Сохранение пользователя: {username}, {last_name} {first_name} {_ex}')
                    try:
                        obj_item, created = UserProfile.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**personal_kwargs})
                    except Exception as _ex:
                        logger.error(f'Сохранение профиля пользователя: {_ex}')
                    if not main_obj_item.user_profile:
                        try:
                            main_obj_item.user_profile = UserProfile.objects.get(ref_key=main_obj_item.ref_key)
                            main_obj_item.save()
                        except Exception as _ex:
                            logger.error(f'Сохранения профиля пользователя в модели пользователя: {_ex}')


            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:staff_list')
            return redirect(url_match)

        return super(StaffListView, self).get(request, *args, **kwargs)


class StaffDetail(LoginRequiredMixin, DetailView):
    template_name = 'customers_app/staff_detail.html'  # Совпадает с именем по умолчании
    model = DataBaseUser


class StaffUpdate(LoginRequiredMixin, UpdateView):
    template_name = 'customers_app/staff_form.html'
    model = DataBaseUser
    form_class = StaffUpdateForm

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа у пользователя к редактированию
            if not DataBaseUser.objects.get(pk=self.request.user.pk).access_level.guide_access_edit:
                # Если права доступа отсутствуют у пользователя, производим перенаправление к списку контрагентов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('customers_app:staff_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку контрагентов
            url_match = reverse_lazy('customers_app:staff_list')
            return redirect(url_match)
        return super(StaffUpdate, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:staff', args=[self.object.pk]))

    def get_context_data(self, **kwargs):
        context = super(StaffUpdate, self).get_context_data(**kwargs)
        context['all_gender'] = DataBaseUser.type_of_gender
        context['all_type_user'] = DataBaseUser.type_of
        context['all_division'] = Division.objects.all()
        context['all_job'] = Job.objects.all()
        context['all_access'] = AccessLevel.objects.all().reverse()
        context['all_citizenship'] = Citizenships.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        content = QueryDict.copy(self.request.POST)

        if content['type_users'] == 'none':
            content.setlist('type_users', '')
        if content['gender'] == 'none':
            content.setlist('gender', '')

        self.request.POST = content
        if self.form_valid:
            obj_user = DataBaseUser.objects.get(pk=kwargs['pk'])
            contracts_access_view = AccessLevel.objects.get(pk=int(content['contracts_access_view']))
            posts_access_view = AccessLevel.objects.get(pk=int(content['posts_access_view']))
            guide_access_view = AccessLevel.objects.get(pk=int(content['guide_access_view']))
            documents_access_view = AccessLevel.objects.get(pk=int(content['documents_access_view']))
            # Формируем словарь записей, которые будем записывать, поля job и division обрабатываем отдельно
            work_kwargs = {
                'date_of_employment': content['date_of_employment'] if content['date_of_employment'] != '' else None,
                'internal_phone': content['internal_phone'],
                'work_phone': content['work_phone'],
                'work_email': content['work_email'],
                'work_email_password': content['work_email_password']
            }
            # Формируем словарь записей, которые будем записывать, поля citizenship и passport обрабатываем отдельно
            personal_kwargs = {
                'snils': content['snils'],
                'oms': content['oms'],
                'inn': content['inn'],
            }
            identity_documents_kwargs = {
                'series': content['series'],
                'number': content['number'],
                'issued_by_whom': content['issued_by_whom'],
                'date_of_issue': content['date_of_issue'] if content['date_of_issue'] != '' else None,
                'division_code': content['division_code'],
            }
            # Если поле job не является пустым, расширяем словарь. То же самое делем с division
            if content['job'] != 'none':
                work_kwargs['job'] = Job.objects.get(pk=content['job'])
            if content['divisions'] != 'none':
                work_kwargs['divisions'] = Division.objects.get(pk=content['divisions'])
            if content['citizenship'] != 'none':
                personal_kwargs['citizenship'] = Citizenships.objects.get(pk=content['citizenship'])
            if not obj_user.user_work_profile:
                obj_work_profile = DataBaseUserWorkProfile(**work_kwargs)
                obj_work_profile.save()
                obj_user.user_work_profile = obj_work_profile
            else:
                obj_work_profile = DataBaseUserWorkProfile.objects.get(pk=obj_user.user_work_profile.pk)
                # Если поле job или division пришли пустыми, присваиваем None значению поля и сохраняем
                if content['job'] == 'none':
                    obj_work_profile.job = None
                    obj_work_profile.save()
                if content['divisions'] == 'none':
                    obj_work_profile.divisions = None
                    obj_work_profile.save()
                obj_work_profile = DataBaseUserWorkProfile.objects.filter(pk=obj_user.user_work_profile.pk)
                obj_work_profile.update(**work_kwargs)

            if not obj_user.user_profile:
                obj_personal_profile_identity_documents = IdentityDocuments(**identity_documents_kwargs)
                obj_personal_profile_identity_documents.save()
                personal_kwargs['passport'] = obj_personal_profile_identity_documents
                obj_personal_profile = UserProfile(**personal_kwargs)
                obj_personal_profile.save()
                obj_user.user_profile = obj_personal_profile
            else:
                try:
                    obj_personal_profile = UserProfile.objects.get(pk=obj_user.user_profile.pk)
                    try:
                        obj_personal_profile_identity_documents = IdentityDocuments.objects.filter(
                            pk=obj_personal_profile.passport.pk)
                        obj_personal_profile_identity_documents.update(**identity_documents_kwargs)
                    except Exception as _ex:
                        message = f'Ошибка сохранения профиля. У пользователя |{obj_user.username}| отсутствует данные паспорта!!!: {_ex}'
                        logger.error(message)
                    if content['citizenship'] == 'none':
                        obj_personal_profile.citizenship = None
                        obj_personal_profile.save()
                    obj_personal_profile = UserProfile.objects.filter(pk=obj_user.user_profile.pk)
                    obj_personal_profile.update(**personal_kwargs)
                except Exception as _ex:
                    message = f'Ошибка сохранения профиля. У пользователя |{obj_user.username}| отсутствует личный профиль!!!: {_ex}'
                    logger.error(message)
            access_kwargs = {
                'contracts_access_view': contracts_access_view,
                'contracts_access_add': boolean_return(request, 'contracts_access_add'),
                'contracts_access_edit': boolean_return(request, 'contracts_access_edit'),
                'contracts_access_agreement': boolean_return(request, 'contracts_access_agreement'),
                'documents_access_view': documents_access_view,
                'documents_access_add': boolean_return(request, 'documents_access_add'),
                'documents_access_edit': boolean_return(request, 'documents_access_edit'),
                'documents_access_agreement': boolean_return(request, 'documents_access_agreement'),
                'posts_access_view': posts_access_view,
                'posts_access_add': boolean_return(request, 'posts_access_add'),
                'posts_access_edit': boolean_return(request, 'posts_access_edit'),
                'posts_access_agreement': boolean_return(request, 'posts_access_agreement'),
                'guide_access_view': guide_access_view,
                'guide_access_add': boolean_return(request, 'guide_access_add'),
                'guide_access_edit': boolean_return(request, 'guide_access_edit'),
                'guide_access_agreement': boolean_return(request, 'guide_access_agreement')
            }
            if not obj_user.access_level:
                obj_access = UserAccessMode(**access_kwargs)
                obj_access.save()
                obj_user.access_level = obj_access
            else:
                obj_access = UserAccessMode.objects.filter(pk=obj_user.access_level.pk)
                obj_access.update(**access_kwargs)
            obj_user.save()
        return super(StaffUpdate, self).post(request, *args, **kwargs)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Подразделения: Список, Добавление, Детализация, Обновление
"""


class DivisionsList(LoginRequiredMixin, ListView):
    model = Division
    template_name = 'customers_app/divisions_list.html'

    def get(self, request, *args, **kwargs):
        count = 0
        if self.request.GET:
            todos = get_jsons_data("Catalog", "ПодразделенияОрганизаций", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Description'] != "":
                    parent_category = True if Division.objects.filter(
                        ref_key=item['Parent_Key']).count() == 1 else False
                    divisions_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'parent_category': Division.objects.get(
                            ref_key=item['Parent_Key']) if parent_category else None,
                        'code': item['Code'],
                        'name': item['Description'],
                        'description': item['Description'],
                        'history': datetime.datetime.strptime(item['ДатаСоздания'][:10], "%Y-%m-%d"),
                        'okved': item['КодОКВЭД2'],
                        'active': False if item['Расформировано'] else True,
                    }
                    Division.objects.update_or_create(ref_key=item['Ref_Key'], defaults=divisions_kwargs)
                        # db_instance = Division(**divisions_kwargs)
                        # db_instance.save()
                        # count += 1
            all_divisions = Division.objects.filter(parent_category=None)
            for item in todos['value']:
                if item['Description'] != "" and item['Parent_Key'] != "00000000-0000-0000-0000-000000000000":
                    if all_divisions.filter(ref_key=item['Ref_Key']).count() == 1:
                        division = Division.objects.get(ref_key=item['Ref_Key'])
                        division.parent_category = Division.objects.get(ref_key=item['Parent_Key'])
                        division.save()
            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:divisions_list')
            return redirect(url_match)

        return super(DivisionsList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Division.objects.filter(active=True).order_by('code')
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        return context


class DivisionsAdd(LoginRequiredMixin, CreateView):
    model = Division
    form_class = DivisionsAddForm
    template_name = 'customers_app/divisions_add.html'

    def get_context_data(self, **kwargs):
        content = super(DivisionsAdd, self).get_context_data(**kwargs)
        content['all_divisions'] = Division.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        """
        Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.guide_access_add:
                return super(DivisionsAdd, self).get(request, *args, **kwargs)
            else:
                url_match = reverse_lazy('customers_app:divisions_list')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('customers_app:divisions_list')
            return redirect(url_match)

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            content = QueryDict.copy(self.request.POST)
            content['history'] = datetime.datetime.now()
            if content['parent_category'] == 'none':
                content.setlist('parent_category', '')
            self.request.POST = content
        return super(DivisionsAdd, self).post(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:divisions_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class DivisionsDetail(LoginRequiredMixin, DetailView):
    model = Division
    template_name = 'customers_app/divisions_detail.html'


class DivisionsUpdate(LoginRequiredMixin, UpdateView):
    model = Division
    template_name = 'customers_app/divisions_update.html'
    form_class = DivisionsUpdateForm

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа у пользователя к редактированию
            if not DataBaseUser.objects.get(pk=self.request.user.pk).access_level.guide_access_edit:
                # Если права доступа отсутствуют у пользователя, производим перенаправление к списку контрагентов
                # Иначе не меняем логику работы класса
                message = f'Попытка получения доступа к изменению. Пользователь {self.request.user.username}, Подразделение {self.get_object()}'
                logger.info(message)
                url_match = reverse_lazy('customers_app:divisions_list')
                return redirect(url_match)
        except Exception as _ex:
            message = f'Ошибка получения прав доступа к изменению. Пользователь {self.request.user.username}, {_ex}'
            logger.error(message)
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку контрагентов
            url_match = reverse_lazy('customers_app:divisions_list')
            return redirect(url_match)
        return super(DivisionsUpdate, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        """
        Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.guide_access_edit:
                return super(DivisionsUpdate, self).get(request, *args, **kwargs)
            else:
                url_match = reverse_lazy('customers_app:divisions_list')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('customers_app:divisions_list')
            return redirect(url_match)

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            content = QueryDict.copy(self.request.POST)
            content['active'] = boolean_return(request, 'active')
            if content['parent_category'] == 'none':
                content.setlist('parent_category', '')
            self.request.POST = content
        return super(DivisionsUpdate, self).post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        content = super(DivisionsUpdate, self).get_context_data(**kwargs)
        content['all_divisions'] = Division.objects.all()
        return content

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:divisions', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Должности: Список, Добавление, Детализация, Обновление
"""


class JobsList(LoginRequiredMixin, ListView):
    model = Job
    template_name = 'customers_app/jobs_list.html'
    paginate_by = 6
    item_sorted = 'pk'
    sorted_list = ['pk', 'code', 'name', 'date_entry']

    def get(self, request, *args, **kwargs):
        count = 0
        change_session_get(request, self)
        if self.request.GET.get('update') == '0':
            todos = get_jsons_data("Catalog", "Должности", 0)
            todos2 = get_jsons_data("Catalog", "ТрудовыеФункции", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['Description'] != "" and item['ВведенаВШтатноеРасписание']:
                    jobs_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'code': '',
                        'name': item['Description'],
                        'date_entry': datetime.datetime.strptime(item['ДатаВвода'][:10], "%Y-%m-%d"),
                        'employment_function': item['ТрудоваяФункция_Key'],
                        'date_exclusions': datetime.datetime.strptime(item['ДатаИсключения'][:10], "%Y-%m-%d"),
                        'excluded_standard_spelling': item['ИсключенаИзШтатногоРасписания']
                    }
                    Job.objects.update_or_create(ref_key=item['Ref_Key'], defaults={**jobs_kwargs})
                        # db_instance = Job(**jobs_kwargs)
                        # db_instance.save()
                        # count += 1
            for item in todos2['value']:
                object_list = Job.objects.filter(employment_function=item['Ref_Key'])
                for unit in object_list:
                    unit.code = item['ОКПДТРКод']
                    unit.save()

            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)

        return super(JobsList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        change_session_queryset(self.request, self)
        qs = Job.objects.filter(excluded_standard_spelling=False).order_by(self.item_sorted)
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(JobsList, self).get_context_data(**kwargs)
        context['title'] = 'Должности'
        change_session_context(context, self)
        return context


class JobsAdd(LoginRequiredMixin, CreateView):
    model = Job
    form_class = JobsAddForm
    template_name = 'customers_app/jobs_add.html'

    def get_context_data(self, **kwargs):
        content = super(JobsAdd, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        """
        Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.guide_access_add:
                return super(JobsAdd, self).get(request, *args, **kwargs)
            else:
                url_match = reverse_lazy('customers_app:jobs_list')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class JobsDetail(LoginRequiredMixin, DetailView):
    model = Job
    template_name = 'customers_app/jobs_detail.html'


class JobsUpdate(LoginRequiredMixin, UpdateView):
    model = Job
    template_name = 'customers_app/jobs_update.html'
    form_class = JobsUpdateForm

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа у пользователя к редактированию
            if not DataBaseUser.objects.get(pk=self.request.user.pk).access_level.guide_access_edit:
                # Если права доступа отсутствуют у пользователя, производим перенаправление к списку контрагентов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('customers_app:jobs_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку контрагентов
            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)
        return super(JobsUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        content = super(JobsUpdate, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        """
        Проверка прав доступа на изменение записи. Если прав нет, то пользователь перенаправляется в общую базу.
        """
        pk = int(self.request.user.pk)
        try:
            if DataBaseUser.objects.get(pk=pk).access_level.guide_access_edit:
                return super(JobsUpdate, self).get(request, *args, **kwargs)
            else:
                url_match = reverse_lazy('customers_app:jobs_list')
                return redirect(url_match)
        except Exception as _ex:
            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Вредные условия труда: Список, Добавление, Детализация, Обновление
"""


class HarmfulWorkingConditionsList(LoginRequiredMixin, ListView):
    model = HarmfulWorkingConditions

    def get(self, request, *args, **kwargs):
        count = 0
        if self.request.GET:
            todos = get_jsons_data("Catalog", "ВредныеОпасныеПроизводственныеФакторыИВыполняемыеРаботы", 0)
            # ToDo: Счетчик добавленных подразделений из 1С. Подумать как передать его значение
            for item in todos['value']:
                if item['IsFolder'] != True:
                    harmful_kwargs = {
                        'ref_key': item['Ref_Key'],
                        'code': item['Code'],
                        'name': item['Description'],
                        'frequency_inspection': item['ПериодичностьОсмотра'],
                        'frequency_multiplicity': item['КратностьОсмотра'],
                    }
                    if HarmfulWorkingConditions.objects.filter(ref_key=item['Ref_Key']).count() != 1:
                        db_instance = HarmfulWorkingConditions(**harmful_kwargs)
                        db_instance.save()
                        count += 1

            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:harmfuls_list')
            return redirect(url_match)
        return super(HarmfulWorkingConditionsList, self).get(request, *args, **kwargs)

    # def get_queryset(self):
    #     qs = Job.objects.filter(excluded_standard_spelling=False)
    #     return qs
