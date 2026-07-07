from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from .models import CreditAgreement
from dateutil.relativedelta import relativedelta


class IsSuperUser(BasePermission):
    """
    Разрешает доступ только суперадминистраторам.
    """

    def has_permission(self, request, view):
        # Проверяем, что пользователь авторизован и является суперпользователем
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class OverdraftListAPIView(APIView):
    """
    API endpoint that allows overdrafts to be viewed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agreements = CreditAgreement.objects.select_related('bank').prefetch_related('tranches',
                                                                                     'payment_facts').all().filter(
            employee=0)
        data = []
        for a in agreements:
            total_tranches = sum(t.amount for t in a.tranches.all())
            total_payments = sum(p.amount for p in a.payment_facts.all() if p.payment_type == 'principal')
            used = total_tranches - total_payments
            available = a.amount - used
            end_date = a.contract_date + relativedelta(months=a.term_months)
            data.append({
                "id": a.id,
                "bank": a.bank.short_name if a.bank else "Неизвестный банк",
                "limit": float(a.amount),
                "used_amount": float(used),
                "available_amount": float(available),
                "interest_rate": float(a.interest_rate),
                "end_date": str(end_date)
            })
        return Response(data)
