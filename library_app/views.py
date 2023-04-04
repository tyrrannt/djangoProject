from django.shortcuts import redirect, render


# Create your views here.

def index(request):
    # return render(request, 'library_app/base.html')
    return redirect('/users/login/')


def show_403(request, exception=None):
    return render(request, 'library_app/403.html')


def show_404(request, exception=None):
    return render(request, 'library_app/404.html')
