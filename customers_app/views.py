import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, CreateView, ListView

from administration_app.models import PortalProperty
from administration_app.utils import boolean_return, get_jsons_data
from contracts_app.models import TypeDocuments, Contract
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


class DataBaseUserProfile(LoginRequiredMixin, DetailView):
    context = {}
    model = DataBaseUser
    template_name = 'customers_app/user_profile.html'

    @method_decorator(user_passes_test(lambda u: u.is_active))
    def dispatch(self, request, *args, **kwargs):
        return super(DataBaseUserProfile, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        post = Posts.objects.all().order_by('creation_date').reverse()
        context = super(DataBaseUserProfile, self).get_context_data(**kwargs)
        context['title'] = 'редактирование'
        context['posts'] = post
        # context.update(groups())
        return context


class DataBaseUserUpdate(LoginRequiredMixin, UpdateView):
    model = DataBaseUser
    template_name = 'customers_app/user_profile_update.html'
    form_class = DataBaseUserUpdateForm

    def get_context_data(self, **kwargs):
        post = Posts.objects.all().order_by('creation_date').reverse()
        context = super(DataBaseUserUpdate, self).get_context_data(**kwargs)
        context['title'] = 'Профиль пользователя'
        context['posts'] = post
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
        if user and user.is_active:
            auth.login(request, user)
            request.session.set_expiry(PortalProperty.objects.get(pk=1).portal_session)
            request.session['portal_paginator'] = PortalProperty.objects.get(pk=1).portal_paginator
            return HttpResponseRedirect(reverse('customers_app:index'))  # , args=(user,))
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
    paginate_by = 5


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
        return reverse("customers_app:post_list", kwargs={"pk": pk})


class CounteragentListView(LoginRequiredMixin, ListView):
    # template_name = 'customers_app/counteragent_list.html'  # Совпадает с именем по умолчании
    model = Counteragent
    paginate_by = 5

    def get_queryset(self):
        qs = Counteragent.objects.all().order_by('pk')
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
                    if Counteragent.objects.filter(ref_key=item['Ref_Key']).count() != 1:
                        db_instance = Counteragent(**divisions_kwargs)
                        db_instance.save()
                        count += 1
            url_match = reverse_lazy('customers_app:counteragent_list')
            return redirect(url_match)

        return super(CounteragentListView, self).get(request, *args, **kwargs)


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
    paginate_by = 5

    def get_queryset(self):
        qs = DataBaseUser.objects.all().order_by('pk')
        return qs


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
                'work_email': content['work_email']
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
                obj_personal_profile = UserProfile.objects.get(pk=obj_user.user_profile.pk)
                obj_personal_profile_identity_documents = IdentityDocuments.objects.filter(
                    pk=obj_personal_profile.passport.pk)
                obj_personal_profile_identity_documents.update(**identity_documents_kwargs)
                if content['citizenship'] == 'none':
                    obj_personal_profile.citizenship = None
                    obj_personal_profile.save()
                obj_personal_profile = UserProfile.objects.filter(pk=obj_user.user_profile.pk)
                obj_personal_profile.update(**personal_kwargs)
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
                    if Division.objects.filter(ref_key=item['Ref_Key']).count() != 1:
                        db_instance = Division(**divisions_kwargs)
                        db_instance.save()
                        count += 1
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
        print(kwargs)
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
                url_match = reverse_lazy('customers_app:divisions_list')
                return redirect(url_match)
        except Exception as _ex:
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

    def get(self, request, *args, **kwargs):
        count = 0
        if self.request.GET:
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
                    if Job.objects.filter(ref_key=item['Ref_Key']).count() != 1:
                        db_instance = Job(**jobs_kwargs)
                        db_instance.save()
                        count += 1
            for item in todos2['value']:
                object_list = Job.objects.filter(employment_function=item['Ref_Key'])
                for unit in object_list:
                    unit.code = item['ОКПДТРКод']
                    unit.save()

            url_match = reverse_lazy('customers_app:jobs_list')
            return redirect(url_match)

        return super(JobsList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Job.objects.filter(excluded_standard_spelling=False)
        return qs


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

