from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import CreditAgreement
from dateutil.relativedelta import relativedelta

class OverdraftListAPIView(APIView):
    """
    API endpoint that allows overdrafts to be viewed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agreements = CreditAgreement.objects.select_related('bank').all()
        data = []
        for a in agreements:
            used = a.remaining_debt
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
