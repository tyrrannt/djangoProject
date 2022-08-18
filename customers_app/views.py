from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, QueryDict
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, CreateView, ListView

from administration_app.models import PortalProperty
from contracts_app.models import TypeDocuments, Contract
from customers_app.models import DataBaseUser, Posts, Counteragent, UserAccessMode
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm, PostsAddForm, \
    CounteragentUpdateForm
from django.contrib import auth, messages
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
    print(types_count)
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
        context['title'] = title = 'редактирование'
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
        context['title'] = title = 'Профиль пользователя'
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
    title = 'вход'
    login_form = DataBaseUserLoginForm(data=request.POST)
    if request.method == 'POST' and login_form.is_valid():
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(username=username, password=password)
        if user and user.is_active:
            auth.login(request, user)
            request.session.set_expiry(PortalProperty.objects.get(pk=1).portal_session)
            request.session['portal_paginator'] = PortalProperty.objects.get(pk=1).portal_paginator
            return HttpResponseRedirect(reverse('customers_app:index'))  # , args=(user.pk,)))
    content = {'title': title, 'login_form': login_form}
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
    template_name = ''
    model = Posts


class CounteragentListView(LoginRequiredMixin, ListView):
    # template_name = 'customers_app/counteragent_list.html'  # Совпадает с именем по умолчании
    model = Counteragent
    paginate_by = 5


class StaffListView(LoginRequiredMixin, ListView):
    template_name = 'customers_app/staff_list.html'
    model = DataBaseUser
    paginate_by = 5

    def get_queryset(self):
        qs = DataBaseUser.objects.filter(type_users='staff_member')
        return qs


class CounteragentDetail(LoginRequiredMixin, DetailView):
    # template_name = 'customers_app/counteragent_detail.html'  # Совпадает с именем по умолчании
    model = Counteragent


class StaffDetail(LoginRequiredMixin, DetailView):
    template_name = 'customers_app/staff_detail.html'  # Совпадает с именем по умолчании
    model = DataBaseUser


class CounteragentUpdate(LoginRequiredMixin, UpdateView):
    # template_name = 'customers_app/counteragent_form.html'  # Совпадает с именем по умолчании
    model = Counteragent
    form_class = CounteragentUpdateForm

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
