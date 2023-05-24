import datetime
import hashlib

from django.core.exceptions import PermissionDenied
from django.db import transaction
from loguru import logger
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, CreateView, ListView

from administration_app.models import PortalProperty
from administration_app.utils import boolean_return, get_jsons_data, \
    change_session_get, change_session_queryset, change_session_context, FIO_format
from contracts_app.models import TypeDocuments, Contract
from customers_app.customers_util import get_database_user_work_profile, get_database_user, get_identity_documents, \
    get_settlement_sheet, get_report_card_table
from customers_app.models import DataBaseUser, Posts, Counteragent, Division, Job, AccessLevel, \
    DataBaseUserWorkProfile, Citizenships, IdentityDocuments, HarmfulWorkingConditions, Groups
from customers_app.models import DataBaseUserProfile as UserProfile
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, PostsAddForm, \
    CounteragentUpdateForm, StaffUpdateForm, DivisionsAddForm, DivisionsUpdateForm, JobsAddForm, JobsUpdateForm, \
    CounteragentAddForm, PostsUpdateForm, GroupAddForm, GroupUpdateForm, ChangePassPraseUpdateForm, \
    ChangeAvatarUpdateForm
from django.contrib import auth
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

from hrdepartment_app.hrdepartment_util import get_report_card
from hrdepartment_app.models import OfficialMemo, ApprovalOficialMemoProcess

logger.add("debug.json", format="{time} {level} {message}", level="DEBUG", rotation="10 MB", compression="zip",
           serialize=True)


class GroupListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Groups
    template_name = 'customers_app/group_list.html'
    success_url = reverse_lazy('customers_app:group_list')
    permission_required = 'customers_app.view_groups'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            group_list = Groups.objects.all()
            data = [group_item.get_data() for group_item in group_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Группы'
        return context


class GroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Groups
    form_class = GroupAddForm
    template_name = 'customers_app/group_form.html'
    success_url = reverse_lazy('customers_app:group_list')
    permission_required = 'customers_app.add_groups'


class GroupUpdateView(LoginRequiredMixin, UpdateView):
    model = Groups
    form_class = GroupUpdateForm
    template_name = 'customers_app/group_form.html'
    success_url = reverse_lazy('customers_app:group_list')


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
        logger.info(f'{_ex}: Отсутствует блок личной информации')
    try:
        for item in get_model_fields(user_work):
            if str(item).split('.')[2] in user_work_list:
                if getattr(user_work, str(item).split('.')[2]):
                    profile_info += 5
    except Exception as _ex:
        logger.info(f'{_ex}: Отсутствует блок рабочей информации')
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
        user_object = self.get_object()
        if request.user.pk == user_object.pk or request.user.is_superuser:
            return super(DataBaseUserProfileDetail, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserProfileDetail, self).get_context_data(**kwargs)
        user_obj = self.get_object()  # DataBaseUser.objects.get(pk=self.request.user.pk)
        post_obj = Posts.objects.all().exclude(post_date_end__lt=datetime.datetime.today())

        try:
            # Получаем выборку постов, у которых дата начала больше текущего дня
            post_high = post_obj.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                        Q(post_date_start__gt=datetime.datetime.today())).order_by(
                '-post_date_start')
            # Получаем выборку постов, у которых дата начала меньше текущего дня
            post_low = post_obj.filter(Q(post_divisions__pk=user_obj.user_work_profile.divisions.pk) &
                                       Q(post_date_start__lte=datetime.datetime.today())).order_by(
                '-post_date_start')
            context['post_high'] = post_high
            context['post_low'] = post_low
        except Exception as _ex:
            message = f'{user_obj}, У пользователя отсутствует подразделение!!!: {_ex}'
            logger.debug(message)

        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Профиль ' + str(FIO_format(user_obj))
        context['sp'] = OfficialMemo.objects.filter(cancellation=False).count()
        context['spf'] = OfficialMemo.objects.filter(cancellation=True).count()
        context['bp'] = ApprovalOficialMemoProcess.objects.filter(cancellation=False).count()
        context['bpf'] = ApprovalOficialMemoProcess.objects.filter(cancellation=True).count()
        context['contract'] = Contract.objects.filter(Q(parent_category=None), Q(allowed_placed=True),
                                                      Q(type_of_document__type_document='Договор')).count()
        context['current_year'] = datetime.datetime.today().year
        context['current_month'] = datetime.datetime.today().month
        get_profile_fill(self, context)

        # context.update(groups())
        return context

    def get(self, request, *args, **kwargs):

        if self.request.GET:
            current_year = self.request.GET.get('CY')
            current_month = self.request.GET.get('CM')
            report_year = self.request.GET.get('RY')
            report_month = self.request.GET.get('RM')
            current_passphrase = self.request.GET.get('PX')
            if current_month and current_year:
                try:
                    if len(current_month) == 1:
                        current_month = '0' + current_month
                    get_user_obj = self.get_object()
                except TypeError:
                    logger.error(f'Ошибка передачи запроса, curent_month не содержит значение!')
                    # ToDo: Пришел запрос с поисковой строки
                    # print(self.request.GET.get('q'))
                    return super().get(request, *args, **kwargs)
                hash_pass = hashlib.sha256(current_passphrase.encode()).hexdigest()
                hash_null = hashlib.sha256(''.encode()).hexdigest()
                if hash_pass == request.user.passphrase and hash_pass != hash_null:
                    html_obj = get_settlement_sheet(current_month, current_year, get_user_obj.person_ref_key)
                else:
                    html_obj = ['', '', '']
                return JsonResponse(html_obj, safe=False)
            if report_year and report_month:
                data_dict, total_score, first_day, last_day = get_report_card(self.request.user.pk, RY=report_year,
                                                                              RM=report_month)
                return JsonResponse(get_report_card_table(data_dict, total_score, first_day, last_day), safe=False)
        return super().get(request, *args, **kwargs)


class ChangePassPraseUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    form_class = ChangePassPraseUpdateForm
    template_name = 'customers_app/change_passphrase.html'


class ChangeAvatarUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    form_class = ChangeAvatarUpdateForm
    template_name = 'customers_app/change_avatar.html'


# class DataBaseUserUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
#     model = DataBaseUser
#     template_name = 'customers_app/user_profile_update.html'
#     form_class = DataBaseUserUpdateForm
#     permission_required = 'customers_app.change_databaseuser'
#
#     def get_context_data(self, **kwargs):
#         context = super(DataBaseUserUpdate, self).get_context_data(**kwargs)
#         user_obj = DataBaseUser.objects.get(pk=self.request.user.pk)
#         try:
#             post = Posts.objects.filter(post_divisions__pk=user_obj.user_work_profile.divisions.pk).order_by(
#                 'creation_date').reverse()
#             context['posts'] = post
#         except Exception as _ex:
#             message = f'{user_obj}, Ошибка получения записей. У пользователя |{user_obj.username}| отсутствует подразделение!!!: {_ex}'
#             logger.error(message)
#
#         context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Профиль пользователя'
#
#         context['sp'] = OfficialMemo.objects.all().count()
#         context['bp'] = ApprovalOficialMemoProcess.objects.all().count()
#         context['contract'] = Contract.objects.all().count()
#         get_profile_fill(self, context)
#         return context
#
#     def get_success_url(self):
#         pk = self.request.user.pk
#         return reverse("customers_app:profile", kwargs={"pk": pk})
#
#     def get(self, request, *args, **kwargs):
#         """
#         Проверка пользователя, при попытке отредактировать профиль другого пользователя путем подстановки в адресной
#         строке чужого ID, будет произведено перенаправление пользователя на свою страницу с профилем.
#         :param request: Передаваемый запрос
#         :param kwargs: Получаем передаваемый ID пользователя из строки в браузере
#         :return: В случае подмены ID выполняет редирект 302
#         """
#         if self.request.user.pk != self.kwargs['pk']:
#             url_match = reverse('customers_app:profile', kwargs={"pk": self.request.user.pk})
#             return redirect(url_match)
#         return super(DataBaseUserUpdate, self).get(request, *args, **kwargs)


def get_client_ip(request):
    # x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    # if x_forwarded_for:
    #     ip = x_forwarded_for.split(',')[0]
    # else:
    #     ip = request.META.get('REMOTE_ADDR')
    # return ip
    x_forwarded_for = request.META.get('HTTP_REMOTE_ADDR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


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
            logger.info(f'Успешный вход. {user}')
            try:
                portal_session = portal.first().portal_session
            except Exception as _ex:
                portal_session = 900
                logger.info(f'{_ex}: Не заданы базовые параметры длительности сессии пользователя')
            try:
                portal_paginator = portal.first().portal_paginator
            except Exception as _ex:
                portal_paginator = 900
                logger.info(f'{_ex}: Не заданы базовые параметры пагинации страниц')
            request.session.set_expiry(portal_session)
            request.session['portal_paginator'] = portal_paginator
            # return HttpResponseRedirect(reverse('customers_app:index'))  # , args=(user,))
            return HttpResponseRedirect(reverse_lazy('customers_app:profile', args=(user.pk,)))  # , args=(user,))
    else:
        try:
            logger.error(f'Ошибка авторизации!!! {request.POST["username"]}, IP: {get_client_ip(request)}')
        except Exception as _ex:
            logger.error(f'Ошибка!!! {_ex}')
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
        # pk = self.request.user.pk
        return reverse("customers_app:post_list")


class CounteragentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    # template_name = 'customers_app/counteragent_list.html'  # Совпадает с именем по умолчании
    model = Counteragent
    paginate_by = 6
    permission_required = 'customers_app.view_counteragent'

    def get_queryset(self):
        qs = Counteragent.objects.all().order_by('pk')
        change_session_queryset(self.request, self)
        return qs

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            counteragent_list = Counteragent.objects.all()
            data = [counteragent_item.get_data() for counteragent_item in counteragent_list]
            response = {'data': data}
            return JsonResponse(response)
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
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Список контрагентов'
        change_session_context(context, self)
        return context


class CounteragentAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Counteragent
    form_class = CounteragentAddForm
    template_name = 'customers_app/counteragent_add.html'
    permission_required = 'customers_app.add_counteragent'

    def get_context_data(self, **kwargs):
        context = super(CounteragentAdd, self).get_context_data(**kwargs)
        context['counteragent_users'] = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
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


class CounteragentDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    # template_name = 'customers_app/counteragent_detail.html'  # Совпадает с именем по умолчании
    model = Counteragent
    permission_required = 'customers_app.view_counteragent'


class CounteragentUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    # template_name = 'customers_app/counteragent_form.html'  # Совпадает с именем по умолчании
    model = Counteragent
    form_class = CounteragentUpdateForm
    permission_required = 'customers_app.change_counteragent'

    def dispatch(self, request, *args, **kwargs):
        return super(CounteragentUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(CounteragentUpdate, self).get_context_data(**kwargs)
        context['counteragent_users'] = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
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


class StaffListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    template_name = 'customers_app/staff_list.html'
    model = DataBaseUser
    paginate_by = 6
    item_sorted = 'pk'
    sorted_list = ['pk', 'last_name', 'user_work_profile__divisions__code', 'user_work_profile__job__name']
    permission_required = 'customers_app.view_databaseuser'

    def get_context_data(self, **kwargs):
        context = super(StaffListView, self).get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Список пользователей'
        change_session_context(context, self)
        return context

    def get_queryset(self):
        change_session_queryset(self.request, self)
        qs = DataBaseUser.objects.all().order_by('pk').exclude(username='proxmox').exclude(is_active=False).order_by(
            self.item_sorted)
        return qs

    def get(self, request, *args, **kwargs):
        change_session_get(request, self)

        if self.request.GET.get('update') == '2':
            get_identity_documents()

        if self.request.GET.get('update') == '1':
            get_database_user_work_profile()

        if self.request.GET.get('update') == '0':
            get_database_user()
            url_match = reverse_lazy('customers_app:staff_list')
            return redirect(url_match)

        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            baseusers = DataBaseUser.objects.all().exclude(username='proxmox').exclude(is_active=False)
            data = [baseuser.get_data() for baseuser in baseusers]
            response = {'data': data}
            return JsonResponse(response)

        return super(StaffListView, self).get(request, *args, **kwargs)


class StaffDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    template_name = 'customers_app/staff_detail.html'  # Совпадает с именем по умолчании
    model = DataBaseUser
    permission_required = 'customers_app.view_databaseuser'

    def dispatch(self, request, *args, **kwargs):
        user_object = self.get_object()
        if request.user.pk == user_object.pk or request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        else:
            logger.warning(f'Пользователь {request.user} хотел получить доступ к пользователю {user_object.username}')
            raise PermissionDenied


class StaffUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = 'customers_app/staff_form.html'
    model = DataBaseUser
    form_class = StaffUpdateForm
    permission_required = 'customers_app.change_databaseuser'

    def dispatch(self, request, *args, **kwargs):
        user_object = self.get_object()
        if request.user.pk == user_object.pk or request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        else:
            logger.warning(f'Пользователь {request.user} хотел получить доступ к пользователю {user_object.username}')
            raise PermissionDenied

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
            # Формируем словарь записей, которые будем записывать, поля job и division обрабатываем отдельно
            work_kwargs = {
                'date_of_employment': content['date_of_employment'] if content['date_of_employment'] != '' else None,
                'internal_phone': content['internal_phone'],
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
                with transaction.atomic():
                    obj_work_profile.save()
                obj_user.user_work_profile = obj_work_profile
            else:
                obj_work_profile = DataBaseUserWorkProfile.objects.get(pk=obj_user.user_work_profile.pk)
                # Если поле job или division пришли пустыми, присваиваем None значению поля и сохраняем
                if content['job'] == 'none':
                    obj_work_profile.job = None
                    with transaction.atomic():
                        obj_work_profile.save()
                if content['divisions'] == 'none':
                    obj_work_profile.divisions = None
                    with transaction.atomic():
                        obj_work_profile.save()
                obj_work_profile = DataBaseUserWorkProfile.objects.filter(pk=obj_user.user_work_profile.pk)
                obj_work_profile.update(**work_kwargs)

            if not obj_user.user_profile:
                obj_personal_profile_identity_documents = IdentityDocuments(**identity_documents_kwargs)
                with transaction.atomic():
                    obj_personal_profile_identity_documents.save()
                personal_kwargs['passport'] = obj_personal_profile_identity_documents
                obj_personal_profile = UserProfile(**personal_kwargs)
                with transaction.atomic():
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
                        with transaction.atomic():
                            obj_personal_profile.save()
                    obj_personal_profile = UserProfile.objects.filter(pk=obj_user.user_profile.pk)
                    obj_personal_profile.update(**personal_kwargs)
                except Exception as _ex:
                    message = f'Ошибка сохранения профиля. У пользователя |{obj_user.username}| отсутствует личный профиль!!!: {_ex}'
                    logger.error(message)
            with transaction.atomic():
                obj_user.save()
        return super(StaffUpdate, self).post(request, *args, **kwargs)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Подразделения: Список, Добавление, Детализация, Обновление
"""


class DivisionsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Division
    template_name = 'customers_app/divisions_list.html'
    permission_required = 'customers_app.view_division'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            divisions_list = Division.objects.filter(active=True)
            data = [divisions_item.get_data() for divisions_item in divisions_list]
            response = {'data': data}
            return JsonResponse(response)
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
                        with transaction.atomic():
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
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Подразделения'
        return context


class DivisionsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Division
    form_class = DivisionsAddForm
    template_name = 'customers_app/divisions_add.html'
    permission_required = 'customers_app.add_division'

    def get_context_data(self, **kwargs):
        content = super(DivisionsAdd, self).get_context_data(**kwargs)
        content['all_divisions'] = Division.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(DivisionsAdd, self).get(request, *args, **kwargs)

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


class DivisionsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Division
    template_name = 'customers_app/divisions_detail.html'
    permission_required = 'customers_app.view_division'


class DivisionsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Division
    template_name = 'customers_app/divisions_update.html'
    form_class = DivisionsUpdateForm
    permission_required = 'customers_app.change_division'

    def dispatch(self, request, *args, **kwargs):
        return super(DivisionsUpdate, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super(DivisionsUpdate, self).get(request, *args, **kwargs)

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


class JobsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Job
    template_name = 'customers_app/jobs_list.html'
    paginate_by = 6
    item_sorted = 'pk'
    sorted_list = ['pk', 'code', 'name', 'date_entry']
    permission_required = 'customers_app.view_job'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            job_list = Job.objects.filter(excluded_standard_spelling=False)
            data = [job_item.get_data() for job_item in job_list]
            response = {'data': data}
            return JsonResponse(response)
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
                    with transaction.atomic():
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
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Должности'
        change_session_context(context, self)
        return context


class JobsAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Job
    form_class = JobsAddForm
    template_name = 'customers_app/jobs_add.html'
    permission_required = 'customers_app.add_job'

    def get_context_data(self, **kwargs):
        content = super(JobsAdd, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(JobsAdd, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs_list'))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class JobsDetail(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Job
    template_name = 'customers_app/jobs_detail.html'
    permission_required = 'customers_app.view_job'


class JobsUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Job
    template_name = 'customers_app/jobs_update.html'
    form_class = JobsUpdateForm
    permission_required = 'customers_app.change_job'

    def dispatch(self, request, *args, **kwargs):
        return super(JobsUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        content = super(JobsUpdate, self).get_context_data(**kwargs)
        content['harmful'] = HarmfulWorkingConditions.objects.all()
        return content

    def get(self, request, *args, **kwargs):
        return super(JobsUpdate, self).get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.is_valid():
            form.save()
        return HttpResponseRedirect(reverse('customers_app:jobs', args=[self.object.pk]))

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


"""
Вредные условия труда: Список, Добавление, Детализация, Обновление
"""


class HarmfulWorkingConditionsList(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = HarmfulWorkingConditions
    permission_required = 'customers_app.view_harmfulworkingconditions'

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            harmful_list = HarmfulWorkingConditions.objects.all()
            data = [harmful_item.get_data() for harmful_item in harmful_list]
            response = {'data': data}
            return JsonResponse(response)
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
                        with transaction.atomic():
                            db_instance.save()
                        count += 1

            # self.get_context_data(object_list=None, kwargs={'added': count})
            url_match = reverse_lazy('customers_app:harmfuls_list')
            return redirect(url_match)
        return super(HarmfulWorkingConditionsList, self).get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Вредные условия труда'
        return context
