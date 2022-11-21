from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView

from customers_app.models import DataBaseUser, Counteragent
from hrdepartment_app.forms import MedicalExaminationAddForm, MedicalExaminationUpdateForm, OfficialMemoUpdateForm, \
    OfficialMemoAddForm
from hrdepartment_app.models import Medical, OfficialMemo


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
        content['all_person'] = DataBaseUser.objects.filter(type_users='staff_member')
        content['all_contragent'] = Counteragent.objects.all()
        content['all_status'] = Medical.type_of
        content['all_harmful'] = ''
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:medical_list')
        # return reverse_lazy('hrdepartment_app:', {'pk': self.object.pk})


class OfficialMemoUpdate(LoginRequiredMixin, UpdateView):
    model = OfficialMemo
    form_class = OfficialMemoUpdateForm
    #template_name = 'hrdepartment_app/oficialmemo_form.html'

    def get_context_data(self, **kwargs):
        content = super(OfficialMemoUpdate, self).get_context_data(**kwargs)
        # content['all_person'] = DataBaseUser.objects.all()
        # content['all_contragent'] = Counteragent.objects.all()
        # content['all_status'] = Medical.type_of
        # content['all_harmful'] = DataBaseUser.objects.get(pk=self.object.person.pk).user_work_profile.job.harmful.iterator()
        return content

    def get_success_url(self):
        return reverse_lazy('hrdepartment_app:memo_list')

