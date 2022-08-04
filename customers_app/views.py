from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, CreateView

from administration_app.models import PortalProperty
from customers_app.models import DataBaseUser, Posts
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm, PostsAddForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test


# Create your views here.

def index(request):
    return render(request, 'customers_app/main.html')


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
            return HttpResponseRedirect(reverse('customers_app:profile', args=(user.pk,)))
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
