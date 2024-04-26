from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView

from administration_app.utils import ajax_search
from customers_app.models import DataBaseUser
from hrdepartment_app.models import ApprovalOficialMemoProcess
from logistics_app.forms import WayBillCreateForm, WayBillUpdateForm, PackageCreateForm, WayBillInlineFormSet
from logistics_app.models import WayBill, Package


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
            search_list = ['document_date', 'place_of_departure__name',
                           'content', 'comment', 'place_division__name',
                           'sender__title', 'state', 'responsible__title', 'date_of_creation',
                           'executor__title', 'urgency'
                           ]
            context = ajax_search(request, self, search_list, Package, query)
            return JsonResponse(context, safe=False)
        return super().get(request, *args, **kwargs)

class PackageInline():
    form_class = PackageCreateForm
    model = Package
    template_name = "logistics_app/package_form.html"

    def form_valid(self, form):
        named_formsets = self.get_named_formsets()
        if not all((x.is_valid() for x in named_formsets.values())):
            return self.render_to_response(self.get_context_data(form=form))

        self.object = form.save()

        # for every formset, attempt to find a specific formset save function
        # otherwise, just save.
        for name, formset in named_formsets.items():
            formset_save_func = getattr(self, 'formset_{0}_valid'.format(name), None)
            if formset_save_func is not None:
                formset_save_func(formset)
            else:
                formset.save()
        return redirect('products:list_products')

    def formset_waybill_valid(self, formset):
        """
        Hook for custom formset saving.Useful if you have multiple formsets
        """
        variants = formset.save(commit=False)  # self.save_formset(formset, contact)
        # add this 2 lines, if you have can_delete=True parameter
        # set in inlineformset_factory func
        for obj in formset.deleted_objects:
            obj.delete()
        for variant in variants:
            variant.product = self.object
            variant.save()

class PackageCreateView(LoginRequiredMixin, PackageInline, CreateView):
    model = Package
    form_class = PackageCreateForm
    get_success_url = '/logistics/waybill/'

    def get_context_data(self, **kwargs):
        ctx = super(PackageCreateView, self).get_context_data(**kwargs)
        ctx['named_formsets'] = self.get_named_formsets()
        return ctx

    def get_named_formsets(self):
        if self.request.method == "GET":
            return {
                'variants': WayBillInlineFormSet(prefix='variants'),
            }
        else:
            return {
                'variants': WayBillInlineFormSet(self.request.POST or None, self.request.FILES or None, prefix='variants'),
            }