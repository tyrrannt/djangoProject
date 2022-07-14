from django.shortcuts import render, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView
from customers_app.models import DataBaseUser
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test


# Create your views here.

def index(request):
    return render(request, 'customers_app/base.html')


class DataBaseUserProfile(DetailView):
    context = {}
    model = DataBaseUser
    template_name = 'customers_app/user_profile.html'

    @method_decorator(user_passes_test(lambda u: u.is_active))
    def dispatch(self, request, *args, **kwargs):
        return super(DataBaseUserProfile, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserProfile, self).get_context_data(**kwargs)
        context['title'] = title = 'редактирование'
        #context.update(groups())
        return context


class DataBaseUserUpdate(UpdateView):
    model = DataBaseUser
    template_name = 'customers_app/user_profile_update.html'
    #success_url = reverse_lazy('library_app:index')
    form_class = DataBaseUserUpdateForm
    #fields = ['first_name', 'last_name', 'email', 'birthday', 'phone', 'surname']

    @method_decorator(user_passes_test(lambda u: u.is_superuser))
    def dispatch(self, request, *args, **kwargs):
        return super(DataBaseUserUpdate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(DataBaseUserUpdate, self).get_context_data(**kwargs)
        context['title'] = title = 'Профиль пользователя'
        return context

    def get_success_url(self):
        pk = self.kwargs["pk"]
        return reverse("customers_app:profile", kwargs={"pk": pk})


def login(request):
    title = 'вход'
    login_form = DataBaseUserLoginForm(data=request.POST)
    if request.method == 'POST' and login_form.is_valid():
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(username=username, password=password)
        if user and user.is_active:
            auth.login(request, user)
            return HttpResponseRedirect(reverse('customers_app:profile', args=(user.pk,)))
    content = {'title': title, 'login_form': login_form}
    return render(request, 'customers_app/login.html', content)


def logout(request):
    auth.logout(request)
    return HttpResponseRedirect(reverse('customers_app:login'))


def register(request):
    title = 'регистрация'
    if request.method == 'POST':
        register_form = DataBaseUserRegisterForm(request.POST, request.FILES)
        if register_form.is_valid():
            user = register_form.save()
            messages.success(request, 'Вы успешно зарегистрировались!')
            # if send_verify_mail(user):
            #     print('сообщение подтверждения отправлено')
            #     return HttpResponseRedirect(reverse('auth:login'))
            # else:
            #     print('ошибка отправки сообщения')
            #     return HttpResponseRedirect(reverse('auth:login'))
    else:
        register_form = DataBaseUserRegisterForm()
    content = {'title': title, 'register_form': register_form}
    return render(request, 'customers_app/register.html', content)
