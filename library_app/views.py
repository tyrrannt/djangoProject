from decouple import config
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from loguru import logger

from administration_app.models import PortalProperty
from library_app.forms import HelpItemAddForm, HelpItemUpdateForm, DocumentFormAddForm, DocumentFormUpdateForm
from library_app.models import HelpTopic, HelpCategory, DocumentForm

# Create your views here.
# logger.add("debug.json", format=config('LOG_FORMAT'), level=config('LOG_LEVEL'),
#            rotation=config('LOG_ROTATION'), compression=config('LOG_COMPRESSION'),
#            serialize=config('LOG_SERIALIZE'))


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


class HelpItem(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = HelpTopic
    permission_required = 'library_app.view_helptopic'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // {self.get_object()}'
        return context


class HelpItemAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = HelpTopic
    form_class = HelpItemAddForm
    permission_required = 'library_app.add_helptopic'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить справку'
        return context


class HelpItemUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = HelpTopic
    form_class = HelpItemUpdateForm
    permission_required = 'library_app.change_helptopic'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование: {self.get_object()}'
        return context


class DocumentFormList(LoginRequiredMixin, ListView):
    model = DocumentForm

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=None, **kwargs)
        context['help_category'] = DocumentForm.objects.all()
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Бланки документов'
        return context

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            dcumentform_list = DocumentForm.objects.all()
            data = [dcumentform_item.get_data() for dcumentform_item in dcumentform_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class DocumentFormItem(PermissionRequiredMixin, LoginRequiredMixin, DetailView):
    model = DocumentForm
    permission_required = 'library_app.view_documentform'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // {self.get_object()}'
        return context


class DocumentFormAdd(PermissionRequiredMixin, LoginRequiredMixin, CreateView):
    model = DocumentForm
    form_class = DocumentFormAddForm
    permission_required = 'library_app.add_documentform'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Добавить бланк'
        return context

    def get_success_url(self):
        return reverse_lazy('library_app:blank_list')
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs


class DocumentFormUpdate(PermissionRequiredMixin, LoginRequiredMixin, UpdateView):
    model = DocumentForm
    form_class = DocumentFormUpdateForm
    template_name = 'library_app/documentform_form_update.html'
    permission_required = 'library_app.change_documentform'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'{PortalProperty.objects.all().last().portal_name} // Редактирование: {self.get_object()}'
        return context

    def get_success_url(self):
        return reverse('library_app:blank', kwargs={'pk': self.object.pk})

    def get_form_kwargs(self):
        """
        Передаем в форму текущего пользователя. В форме переопределяем метод __init__
        :return: PK текущего пользователя
        """
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user.pk})
        return kwargs
