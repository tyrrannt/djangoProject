from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import ListView, DetailView, CreateView, UpdateView

from administration_app.models import PortalProperty
from library_app.forms import HelpItemAddForm, HelpItemUpdateForm
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
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Справка'
        return context

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            helptopic_list = HelpTopic.objects.all()
            data = [helptopic_item.get_data() for helptopic_item in helptopic_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class HelpItem(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = HelpTopic
    permission_required = 'library_app.view_helptopic'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // {self.get_object()}'
        return context


class HelpItemAdd(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = HelpTopic
    form_class = HelpItemAddForm
    permission_required = 'library_app.add_helptopic'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить справку'
        return context


class HelpItemUpdate(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = HelpTopic
    form_class = HelpItemUpdateForm
    permission_required = 'library_app.change_helptopic'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование: {self.get_object()}'
        return context