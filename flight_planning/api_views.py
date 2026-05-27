# flight_planning/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics
from django.utils import timezone
from .models import PilotAssignment
from hrdepartment_app.models import PlaceProductionActivity
from .selectors import get_pilot_assignments_for_month
from .services import get_grouped_pilot_schedule
from .serializers import GroupedScheduleSerializer, MPDSerializer

class MyScheduleAPIView(APIView):
    """
    API View to get the authenticated pilot's grouped schedule for a given month.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
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
    """
    API View to list all planning-enabled MPDs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MPDSerializer
    queryset = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')
