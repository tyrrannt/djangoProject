import datetime
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

from administration_app.utils import change_session_context, change_session_queryset, change_session_get
from customers_app.models import DataBaseUser, Counteragent
from hrdepartment_app.forms import MedicalExaminationAddForm, MedicalExaminationUpdateForm, OfficialMemoUpdateForm, \
    OfficialMemoAddForm, ApprovalOficialMemoProcessAddForm, ApprovalOficialMemoProcessUpdateForm
from hrdepartment_app.models import Medical, OfficialMemo, ApprovalOficialMemoProcess


# Create your views here.

class MedicalExamination(LoginRequiredMixin, ListView):
    model = Medical


class MedicalExaminationAdd(LoginRequiredMixin, CreateView):
    model = Medical
    form_class = MedicalExaminationAddForm

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationAdd, self).get_context_data(**kwargs)
        content['all_person'] = DataBaseUser.objects.filter(type_users='staff_member')
        content['all_contragent'] = Counteragent.objects.all()
        content['all_status'] = Medical.type_of
        content['all_harmful'] = ''
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class MedicalExaminationUpdate(LoginRequiredMixin, UpdateView):
    model = Medical
    form_class = MedicalExaminationUpdateForm
    template_name = 'hrdepartment_app/medical_form_update.html'

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationUpdate, self).get_context_data(**kwargs)
        # content['all_person'] = DataBaseUser.objects.all()
        # content['all_contragent'] = Counteragent.objects.all()
        # content['all_status'] = Medical.type_of
        content['all_harmful'] = DataBaseUser.objects.get(
            pk=self.object.person.pk).user_work_profile.job.harmful.iterator()
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')


class OfficialMemoList(LoginRequiredMixin, ListView):
    model = OfficialMemo
    paginate_by = 6

    def get(self, request, *args, **kwargs):
        change_session_get(self.request, self)
        return super(OfficialMemoList, self).get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super(OfficialMemoList, self).get_queryset()
        change_session_queryset(self.request, self)
        user_division = DataBaseUser.objects.get(pk=self.request.user.pk).user_work_profile.divisions
        qs = OfficialMemo.objects.filter(responsible__user_work_profile__divisions=user_division).order_by('pk').reverse()
        return qs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(OfficialMemoList, self).get_context_data(**kwargs)
        context['title'] = 'Список пользователей'
        change_session_context(context, self)
        return context


class OfficialMemoAdd(LoginRequiredMixin, CreateView):
    model = OfficialMemo
    form_class = OfficialMemoAddForm

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoAdd, self).get_context_data(**kwargs)
        content['all_status'] = OfficialMemo.type_of
        # Генерируем список сотрудников, которые на текущий момент времени не находятся в СП
        users_list = [person.person_id for person in OfficialMemo.objects.filter(
            Q(period_from__lte=datetime.datetime.today()) & Q(period_for__gte=datetime.datetime.today()))]
        # Выбераем из базы тех сотрудников, которые содержатся в списке users_list и исключаем из него суперпользователя
        # content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(pk__in=users_list).exclude(is_superuser=True)
        content['form'].fields['person'].queryset = DataBaseUser.objects.all().exclude(is_superuser=True)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_valid(self, form):
        return super().form_valid(form)

    def get(self, request, *args, **kwargs):
        global min_date
        html = list()
        employee = request.GET.get('employee', None)
        period_from = request.GET.get('period_from', None)
        if employee and period_from:
            check_date = datetime.datetime.strptime(period_from, '%Y-%m-%d')
            filters = OfficialMemo.objects.filter(
                Q(person__pk=employee) & Q(period_from__lte=check_date) & Q(period_for__gte=check_date))
            try:
                min_date = filters.first().period_for
            except AttributeError:
                print('За заданный период СП не найдены')
            if filters.count() > 0:
                html.append(f'<input type="date" id="id_period_from" class="form-control form-control-modern" min="{min_date + datetime.timedelta(days=1)}" ' \
                   f'name="period_from" value="" data-plugin-datepicker data-plugin-options=' + "'" + '{"orientation": "bottom", "format": "yyyy-mm-dd"}' + "'/>")
                html.append(f'<input type="date" id="id_period_for" class="form-control form-control-modern" min="{min_date + datetime.timedelta(days=1)}" ' \
                       f'name="period_for" value="" data-plugin-datepicker data-plugin-options=' + "'" + '{"orientation": "bottom", "format": "yyyy-mm-dd"}' + "'/>")

                return JsonResponse(html, safe=False)


        return super(OfficialMemoAdd, self).get(request, *args, **kwargs)


class OfficialMemoUpdate(LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    template_name = 'hrdepartment_app/officialmemo_form_update.html'

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        period = self.get_object()
        delta = (period.period_for - period.period_from)
        content['period'] = int(delta.days) + 1
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)

    def form_valid(self, form):
        return super().form_valid(form)


class ApprovalOficialMemoProcessList(LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess

    def get_queryset(self):
        user_division = DataBaseUser.objects.get(pk=self.request.user.pk).user_work_profile.divisions

        qs = ApprovalOficialMemoProcess.objects.filter(Q(person_agreement__user_work_profile__divisions=user_division) |
                                                       Q(person_distributor__user_work_profile__divisions=user_division) |
                                                       Q(person_executor__user_work_profile__divisions=user_division) |
                                                       Q(person_department_staff__user_work_profile__divisions=user_division))
        return qs


class ApprovalOficialMemoProcessAdd(LoginRequiredMixin, CreateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm

    def get_context_data(self, **kwargs):
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)
        content['form'].fields['document'].queryset = OfficialMemo.objects.filter(docs__isnull=True)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')


class ApprovalOficialMemoProcessUpdate(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessUpdateForm

    # template_name = 'hrdepartment_app/oficialmemo_form.html'

    def get_context_data(self, **kwargs):
        content = super(ApprovalOficialMemoProcessUpdate, self).get_context_data(**kwargs)
        document = self.get_object()
        content['document'] = document.document
        # content['all_contragent'] = Counteragent.objects.all()
        # content['all_status'] = Medical.type_of
        # content['all_harmful'] = DataBaseUser.objects.get(pk=self.object.person.pk).user_work_profile.job.harmful.iterator()
        return content

    def form_valid(self, form):
        return super().form_valid(form)

    # Проверяем изменения параметров
    def post(self, request, *args, **kwargs):
        """
        Обрабатываем POST запрос. Получаем данные передаваемые в форме. Внутренние переменные:
        data - Дата приказа; number - Номер приказа; accommodation - место проживания; change_status - статус изменения
        документа, 0 - если данные документа не менялись, и 1 - если данные были изменены, document - ссылка на
        служебную записку.

        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        data = request.POST.get('order_date')
        number = request.POST.get('order_number')
        accommodation = request.POST.get('accommodation')
        change_status = 0
        document = OfficialMemo.objects.get(pk=self.get_object().document.pk)
        if document.order_date != data:
            # Если добавлена или изменена дата приказа, сохраняем ее в документ Служебной записки
            if data != '':
                document.order_date = data
                change_status = 1
        print(data)
        if document.order_number != number:
            # Если добавлен или изменен номер приказа, сохраняем его в документ Служебной записки
            document.order_number = number
            change_status = 1
        if document.accommodation != accommodation:
            # Если добавлено или изменено место проживания, сохраняем его в документ Служебной записки
            if accommodation:
                document.accommodation = accommodation
                change_status = 1
        if request.POST.get('submit_for_approval'):
            document.comments = 'Передан на согласование'
            change_status = 1
        else:
            document.comments = 'Документооборот начат'
            change_status = 1
        if request.POST.get('document_not_agreed'):
            document.comments = 'Документ согласован'
            change_status = 1
        if request.POST.get('location_selected'):
            document.comments = 'Утверждено место проживания'
            change_status = 1
        if request.POST.get('process_accepted'):
            document.comments = 'Документооборот завершен'
            document.document_accepted = True
            change_status = 1
        else:
            document.document_accepted = False
            change_status = 1
        if change_status > 0:
            document.save()
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')
