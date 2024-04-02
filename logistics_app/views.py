from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from administration_app.utils import ajax_search
from customers_app.models import DataBaseUser
from hrdepartment_app.models import ApprovalOficialMemoProcess
from logistics_app.forms import WayBillCreateForm, WayBillUpdateForm
from logistics_app.models import WayBill


# Create your views here.

class WayBillListView(LoginRequiredMixin, ListView):
    model = WayBill
    paginate_by = 10

    def get_queryset(self):
        return WayBill.objects.all()

    def get(self, request, *args, **kwargs):
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['document_date', 'place_of_departure__name',
                           'content', 'comment', 'place_division__name',
                           'sender__title', 'state', 'responsible__title', 'date_of_creation',
                           'executor__title', 'urgency'
                           ]
            context = ajax_search(request, self, search_list, WayBill, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)


class WayBillCreateView(LoginRequiredMixin, CreateView):
    model = WayBill
    form_class = WayBillCreateForm
    get_success_url = '/logistics/waybill/'

    def get(self, request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if request.GET.get('term') is not None:
                object_list = WayBill.objects.filter(content__iregex=request.GET.get('term'))
                suggestions = [property_item.content for property_item in object_list]
                print(suggestions)
                return JsonResponse(suggestions, safe=False)
            if request.GET.get('q') is not None:
                object_list = WayBill.objects.filter(comment__iregex=request.GET.get('q'))
                suggestions = [property_item.comment for property_item in object_list]
                print(suggestions)
                return JsonResponse(suggestions, safe=False)
        return super().get(request, *args, **kwargs)


class WayBillDetailView(LoginRequiredMixin, DetailView):
    model = WayBill
    template_name = 'logistics_app/waybill_detail.html'


class WayBillUpdateView(LoginRequiredMixin, UpdateView):
    model = WayBill
    form_class = WayBillUpdateForm


class WayBillDeleteView(LoginRequiredMixin, DeleteView):
    model = WayBill
    success_url = '/logistics/waybill/'
