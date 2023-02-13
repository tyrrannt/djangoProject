from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import DetailView, UpdateView, ListView, CreateView
from contracts_app.models import TypeDocuments
from customers_app.models import DataBaseUser, AccessLevel, Division
from django.urls import reverse_lazy
from library_app.forms import DocumentsJobDescriptionAddForm, DocumentsJobDescriptionUpdateForm
from library_app.models import DocumentsJobDescription


# Create your views here.

def index(request):
    #return render(request, 'library_app/base.html')
    return redirect('/users/login/')


class DocumentsJobDescriptionList(LoginRequiredMixin, ListView):
    model = DocumentsJobDescription

    def get_queryset(self):
        return DocumentsJobDescription.objects.filter(Q(allowed_placed=True))


class DocumentsJobDescriptionAdd(LoginRequiredMixin, CreateView):
    model = DocumentsJobDescription
    form_class = DocumentsJobDescriptionAddForm

    def get_context_data(self, **kwargs):
        content = super(DocumentsJobDescriptionAdd, self).get_context_data(**kwargs)
        content['all_document_types'] = TypeDocuments.objects.all()
        content['all_access'] = AccessLevel.objects.all()
        content['all_employee'] = DataBaseUser.objects.all()
        content['all_divisions'] = Division.objects.all()
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
