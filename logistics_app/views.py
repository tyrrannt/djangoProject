from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from administration_app.utils import ajax_search
from logistics_app.forms import WayBillCreateForm, WayBillUpdateForm, PackageCreateForm
from logistics_app.models import WayBill, Package
from core import logger


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
                suggestions_set = set([property_item.content for property_item in object_list])
                return JsonResponse(list(suggestions_set), safe=False)
            if request.GET.get('q') is not None:
                object_list = WayBill.objects.filter(comment__iregex=request.GET.get('q'))
                suggestions_set = set([property_item.comment for property_item in object_list])
                return JsonResponse(list(suggestions_set), safe=False)
        return super().get(request, *args, **kwargs)


class WayBillDetailView(LoginRequiredMixin, DetailView):
    model = WayBill
    template_name = 'logistics_app/waybill_detail.html'


class WayBillUpdateView(LoginRequiredMixin, UpdateView):
    model = WayBill
    form_class = WayBillUpdateForm
    success_url = '/logistics/waybill/'


class WayBillDeleteView(LoginRequiredMixin, DeleteView):
    model = WayBill
    success_url = '/logistics/waybill/'


class PackageListView(LoginRequiredMixin, ListView):
    model = Package
    paginate_by = 10

    def get_queryset(self):
        return Package.objects.all()

    def get(self, request, *args, **kwargs):
        query = Q()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            search_list = ['date_of_dispatch', 'number_of_dispatch',
                           'place_of_dispatch', "executor__title", "type_of_dispatch"
                           ]
            context = ajax_search(request, self, search_list, Package, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)


class PackageCreateView(LoginRequiredMixin, CreateView):
    model = Package
    form_class = PackageCreateForm
    success_url = reverse_lazy("logistics_app:package_list")

    # https://www.letscodemore.com/blog/django-inline-formset-factory-with-examples/

    def get_context_data(self, **kwargs):
        context = super(PackageCreateView, self).get_context_data(**kwargs)
        context['way_bills'] = WayBill.objects.all()
        return context

    def get(self, request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            if request.GET.get('term') is not None:
                object_list = WayBill.objects.filter(content__iregex=request.GET.get('term'))
                suggestions_set = set([property_item.content for property_item in object_list])
                return JsonResponse(list(suggestions_set), safe=False)
        return super().get(request, *args, **kwargs)
