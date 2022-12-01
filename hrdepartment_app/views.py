from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView

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
        #return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class MedicalExaminationUpdate(LoginRequiredMixin, UpdateView):
    model = Medical
    form_class = MedicalExaminationUpdateForm
    template_name = 'hrdepartment_app/medical_form_update.html'

    def get_context_data(self, **kwargs):
        content = super(MedicalExaminationUpdate, self).get_context_data(**kwargs)
        # content['all_person'] = DataBaseUser.objects.all()
        # content['all_contragent'] = Counteragent.objects.all()
        # content['all_status'] = Medical.type_of
        content['all_harmful'] = DataBaseUser.objects.get(pk=self.object.person.pk).user_work_profile.job.harmful.iterator()
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')


class OfficialMemoList(LoginRequiredMixin, ListView):
    model = OfficialMemo


class OfficialMemoAdd(LoginRequiredMixin, CreateView):
    model = OfficialMemo
    form_class = OfficialMemoAddForm

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoAdd, self).get_context_data(**kwargs)
        content['all_status'] = OfficialMemo.type_of
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')


class OfficialMemoUpdate(LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

    def form_invalid(self, form):
        return super(OfficialMemoUpdate, self).form_invalid(form)


class ApprovalOficialMemoProcessList(LoginRequiredMixin, ListView):
    model = ApprovalOficialMemoProcess

    def get_queryset(self):
        qs = ApprovalOficialMemoProcess.objects.filter(Q(person_agreement=self.request.user) |
                                                       Q(person_distributor=self.request.user) |
                                                       Q(person_executor=self.request.user) |
                                                       Q(person_department_staff=self.request.user))
        return qs


class ApprovalOficialMemoProcessAdd(LoginRequiredMixin, CreateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessAddForm

    def get_context_data(self, **kwargs):
        content = super(ApprovalOficialMemoProcessAdd, self).get_context_data(**kwargs)

        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')



class ApprovalOficialMemoProcessUpdate(LoginRequiredMixin, UpdateView):
    model = ApprovalOficialMemoProcess
    form_class = ApprovalOficialMemoProcessUpdateForm
    #template_name = 'hrdepartment_app/oficialmemo_form.html'

    def get_context_data(self, **kwargs):
        content = super(ApprovalOficialMemoProcessUpdate, self).get_context_data(**kwargs)
        # content['all_person'] = DataBaseUser.objects.all()
        # content['all_contragent'] = Counteragent.objects.all()
        # content['all_status'] = Medical.type_of
        # content['all_harmful'] = DataBaseUser.objects.get(pk=self.object.person.pk).user_work_profile.job.harmful.iterator()
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:bpmemo_list')
