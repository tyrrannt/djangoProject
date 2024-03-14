from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views.generic import ListView

from logistics_app.models import WayBill


# Create your views here.

class WayBillListView(LoginRequiredMixin, ListView):
    model = WayBill
    template_name = 'logistics_app/waybill_list.html'
    context_object_name = 'waybills'
    paginate_by = 10

    def get_queryset(self):
        return WayBill.objects.filter(user=self.request.user)
