from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import QueryDict
from django.shortcuts import render, HttpResponseRedirect, redirect
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, UpdateView, ListView, CreateView

from administration_app.utils import boolean_return
from contracts_app.models import TypeDocuments
from customers_app.models import DataBaseUser, AccessLevel, Division
from customers_app.forms import DataBaseUserLoginForm, DataBaseUserRegisterForm, DataBaseUserUpdateForm
from django.contrib import auth, messages
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required, user_passes_test

from library_app.forms import DocumentsAddForm, DocumentsUpdateForm
from library_app.models import Documents


# Create your views here.

def index(request):
    return render(request, 'library_app/base.html')


class DocumentsList(LoginRequiredMixin, ListView):
    # template_name = ''
    model = Documents

    def get_queryset(self):
        return Documents.objects.filter(Q(allowed_placed=True))


class DocumentsAdd(LoginRequiredMixin, CreateView):
    # template_name = ''
    model = Documents
    form_class = DocumentsAddForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsAdd, self).get_context_data(**kwargs)
        content['all_document_types'] = TypeDocuments.objects.all()
        content['all_access'] = AccessLevel.objects.all()
        content['all_employee'] = DataBaseUser.objects.all()
        content['all_divisions'] = Division.objects.all()
        return content


class DocumentsDetail(LoginRequiredMixin, DetailView):
    # template_name = ''
    model = Documents

    def dispatch(self, request, *args, **kwargs):
        try:
            # Получаем уровень доступа для запрашиваемого объекта
            detail_obj = int(self.get_object().access.level)
            # Получаем уровень доступа к документам у пользователя
            user_obj = DataBaseUser.objects.get(pk=self.request.user.pk).access_level.documents_access_view.level
            # Сравниваем права доступа
            if detail_obj < user_obj:
                # Если права доступа у документа выше чем у пользователя, производим перенаправление к списку документов
                # Иначе не меняем логику работы класса
                url_match = reverse_lazy('library_app:documents_list')
                return redirect(url_match)
        except Exception as _ex:
            # Если при запросах прав произошла ошибка, то перехватываем ее и перенаправляем к списку документов
            url_match = reverse_lazy('library_app:documents_list')
            return redirect(url_match)
        return super(DocumentsDetail, self).dispatch(request, *args, **kwargs)


class DocumentsUpdate(LoginRequiredMixin, UpdateView):
    template_name = 'library_app/documents_update.html'
    model = Documents
    form_class = DocumentsUpdateForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsUpdate, self).get_context_data(**kwargs)
        content['all_document_types'] = TypeDocuments.objects.all()
        content['all_access'] = AccessLevel.objects.all()
        content['all_employee'] = DataBaseUser.objects.all()
        content['all_divisions'] = Division.objects.all()
        return content

    # def post(self, request, *args, **kwargs):
    #     content = QueryDict.copy(self.request.POST)
    #     if content['allowed_placed'] == 'on':
    #         content.setlist('allowed_placed', True)
    #     if content['actuality'] == 'on':
    #         content.setlist('actuality', True)
    #     self.request.POST = content
