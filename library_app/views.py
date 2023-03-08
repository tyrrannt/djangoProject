from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, UpdateView, ListView, CreateView
from contracts_app.models import TypeDocuments
from customers_app.models import DataBaseUser, AccessLevel, Division
from django.urls import reverse_lazy
from library_app.forms import DocumentsJobDescriptionAddForm, DocumentsJobDescriptionUpdateForm, \
    DocumentsOrderUpdateForm, DocumentsOrderAddForm
from library_app.models import DocumentsJobDescription, DocumentsOrder


# Create your views here.

def index(request):
    #return render(request, 'library_app/base.html')
    return redirect('/users/login/')


# Должностные инструкции
class DocumentsJobDescriptionList(LoginRequiredMixin, ListView):
    model = DocumentsJobDescription

    def get_queryset(self):
        return DocumentsJobDescription.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            documents_job_list = DocumentsJobDescription.objects.all()
            data = [documents_job_item.get_data() for documents_job_item in documents_job_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)


class DocumentsJobDescriptionAdd(LoginRequiredMixin, CreateView):
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionAddForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsJobDescriptionAdd, self).get_context_data(**kwargs)
        content['title'] = 'Создание ДИ'
        return content


class DocumentsJobDescriptionDetail(LoginRequiredMixin, DetailView):
    model = DocumentsJobDescription

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
        return super(DocumentsJobDescriptionDetail, self).dispatch(request, *args, **kwargs)


class DocumentsJobDescriptionUpdate(LoginRequiredMixin, UpdateView):
    template_name = 'library_app/documentsjobdescription_update.html'
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionUpdateForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsJobDescriptionUpdate, self).get_context_data(**kwargs)
        content['title'] = 'Изменение ДИ'
        return content


# Приказы
class DocumentsOrderList(LoginRequiredMixin, ListView):
    model = DocumentsOrder

    def get_queryset(self):
        return DocumentsOrder.objects.filter(Q(allowed_placed=True))

    def get(self, request, *args, **kwargs):
        # Определяем, пришел ли запрос как JSON? Если да, то возвращаем JSON ответ
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            documents_order_list = DocumentsOrder.objects.all()
            data = [documents_order_item.get_data() for documents_order_item in documents_order_list]
            response = {'data': data}
            return JsonResponse(response)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Список приказов'
        return context


class DocumentsOrderAdd(LoginRequiredMixin, CreateView):
    model = DocumentsOrder
    form_class = DocumentsOrderAddForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsOrderAdd, self).get_context_data(**kwargs)
        content['title'] = 'Создание приказа'
        return content


class DocumentsOrderDetail(LoginRequiredMixin, DetailView):
    model = DocumentsOrder

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
        return super(DocumentsOrderDetail, self).dispatch(request, *args, **kwargs)


class DocumentsOrderUpdate(LoginRequiredMixin, UpdateView):
    template_name = 'library_app/documentsorder_update.html'
    model = DocumentsOrder
    form_class = DocumentsOrderUpdateForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsOrderUpdate, self).get_context_data(**kwargs)
        content['title'] = 'Изменение приказа'
        return content
