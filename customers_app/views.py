from django.shortcuts import render, HttpResponseRedirect
from customers_app.forms import DataBaseUserLoginForm
from django.contrib import auth, messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required


# Create your views here.

def index(request):
    return render(request, 'customers_app/base.html')


def login(request):
    title = 'вход'
    login_form = DataBaseUserLoginForm(data=request.POST)
    print(request.POST)
    if request.method == 'POST' and login_form.is_valid():
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(username=username, password=password)
        if user and user.is_active:
            auth.login(request, user)
            return HttpResponseRedirect(reverse('customers_app:index'))
    content = {'title': title, 'login_form': login_form}
    return render(request, 'customers_app/login.html', content)


def logout(request):
    auth.logout(request)
    return HttpResponseRedirect(reverse('main'))

def register(request):
    title = 'регистрация'
    if request.method == 'POST':
        register_form = DataBaseUserLoginForm(request.POST, request.FILES)
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
        register_form = DataBaseUserLoginForm()
    content = {'title': title, 'register_form': register_form}
    return render(request, 'customers_app/', content)