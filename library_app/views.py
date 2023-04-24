from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import ListView, DetailView

from library_app.models import HelpTopic, HelpCategory


# Create your views here.

def index(request):
    # return render(request, 'library_app/base.html')
    return redirect('/users/login/')


def show_403(request, exception=None):
    return render(request, 'library_app/403.html')


def show_404(request, exception=None):
    return render(request, 'library_app/404.html')


class HelpList(LoginRequiredMixin, ListView):
    model = HelpTopic

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['help_category'] = HelpCategory.objects.all()

        return context

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            helptopic_list = HelpTopic.objects.all()
            data = [helptopic_item.get_data() for helptopic_item in helptopic_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class HelpItem(LoginRequiredMixin, DetailView):
    model = HelpTopic