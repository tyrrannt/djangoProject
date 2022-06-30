from django.shortcuts import render, HttpResponseRedirect
from customers_app.forms import DataBaseUserLoginForm
from django.contrib import auth
from django.urls import reverse


# Create your views here.

def index(request):
    return render(request, 'customers_app/base.html')


def login(request):
    title = 'вход'
    login_form = DataBaseUserLoginForm(data=request.POST)
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
