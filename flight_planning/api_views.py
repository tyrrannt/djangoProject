# flight_planning/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.utils import timezone
from .models import PilotAssignment
from hrdepartment_app.models import PlaceProductionActivity
from .permissions import CanViewFlightPlanning
from .selectors import get_pilot_assignments_for_month
from .services import get_grouped_pilot_schedule
from .serializers import GroupedScheduleSerializer, MPDSerializer


class MyScheduleAPIView(APIView):
    """API-представление для получения сгруппированного графика текущего пилота за месяц."""

    permission_classes = [IsAuthenticated, CanViewFlightPlanning]

    def get(self, request, *args, **kwargs):
        """Обрабатывает GET-запрос графика пользователя.

        Args:
            request (Request): HTTP-запрос DRF с параметрами 'year' и 'month'.
            *args: Дополнительные позиционные аргументы.
            **kwargs: Дополнительные именованные аргументы.

        Returns:
            Response: Ответ со списком сгруппированных смен графика.
        """
        year = request.query_params.get('year', timezone.now().year)
        month = request.query_params.get('month', timezone.now().month)

        try:
            year = int(year)
            month = int(month)
        except ValueError:
            return Response({'error': 'Invalid year or month'}, status=400)

        assignments = get_pilot_assignments_for_month(
            pilot_id=request.user.id,
            year=year,
            month=month
        )

        grouped_schedule = get_grouped_pilot_schedule(list(assignments), year, month)
        serializer = GroupedScheduleSerializer(grouped_schedule, many=True)
        
        return Response({
            'year': year,
            'month': month,
            'schedule': serializer.data
        })


class MPDListAPIView(generics.ListAPIView):
    """API-представление для получения списка МПД, участвующих в планировании полетов."""

    permission_classes = [IsAuthenticated, CanViewFlightPlanning]
    serializer_class = MPDSerializer
    queryset = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')

