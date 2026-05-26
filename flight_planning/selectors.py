# flight_planning/selectors.py
from django.db.models import QuerySet
from .models import PilotAssignment

def get_pilot_assignments_for_month(pilot_id: int, year: int, month: int) -> QuerySet[PilotAssignment]:
    """
    Returns a list of pilot assignments for the specified month.

    Args:
        pilot_id: ID of the pilot (DataBaseUser).
        year: Year of the assignments.
        month: Month of the assignments.

    Returns:
        QuerySet of PilotAssignment instances.
    """
    return PilotAssignment.objects.filter(
        pilot_id=pilot_id,
        date__year=year,
        date__month=month
    ).select_related('mpd').order_by('date')
