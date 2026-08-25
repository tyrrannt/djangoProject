# flight_planning/selectors.py
from datetime import date, timedelta
from typing import Optional, Dict, List, Any
from django.db.models import QuerySet, Q
from django.utils import timezone
from contracts_app.models import Estate
from .models import PilotAssignment, AircraftMovement, FlightCrew, CrewMember


def get_pilot_assignments_for_month(pilot_id: int, year: int, month: int) -> QuerySet[PilotAssignment]:
    """
    Returns a list of pilot assignments for the specified month.
    """
    return PilotAssignment.objects.filter(
        pilot_id=pilot_id,
        date__year=year,
        date__month=month
    ).select_related('mpd').order_by('date')


def get_active_aircraft(target_date: Optional[date] = None) -> QuerySet[Estate]:
    """
    Возвращает список воздушных судов (Estate), находящихся в эксплуатации на заданную дату.
    """
    if target_date is None:
        target_date = timezone.now().date()

    return Estate.objects.filter(
        Q(decommission_date__isnull=True) | Q(decommission_date__gt=target_date)
    ).select_related('type_property').order_by('registration_number')


def get_latest_aircraft_locations(target_date: Optional[date] = None) -> Dict[int, AircraftMovement]:
    """
    Возвращает последнее актуальное перемещение/базирование для каждого борта на дату target_date.
    """
    if target_date is None:
        target_date = timezone.now().date()

    movements = AircraftMovement.objects.filter(
        date__lte=target_date
    ).select_related('aircraft', 'mpd', 'created_by').order_by('aircraft_id', '-date', '-created_at')

    latest_map: Dict[int, AircraftMovement] = {}
    for movement in movements:
        if movement.aircraft_id not in latest_map:
            latest_map[movement.aircraft_id] = movement

    return latest_map


def get_aircraft_movement_history(aircraft_id: int) -> QuerySet[AircraftMovement]:
    """
    Возвращает полную историю перемещений конкретного воздушного судна.
    """
    return AircraftMovement.objects.filter(
        aircraft_id=aircraft_id
    ).select_related('mpd', 'created_by').order_by('-date', '-created_at')


def get_mpd_aircraft_map(target_date: Optional[date] = None) -> Dict[int, List[Dict[str, Any]]]:
    """
    Возвращает карту распределения активных воздушных судов по МПД на заданную дату.
    """
    active_aircraft_ids = set(get_active_aircraft(target_date).values_list('id', flat=True))
    latest_locations = get_latest_aircraft_locations(target_date)

    mpd_map: Dict[int, List[Dict[str, Any]]] = {}
    for aircraft_id, movement in latest_locations.items():
        if aircraft_id in active_aircraft_ids:
            mpd_id = movement.mpd_id
            if mpd_id not in mpd_map:
                mpd_map[mpd_id] = []
            mpd_map[mpd_id].append({
                'aircraft_id': aircraft_id,
                'registration_number': movement.aircraft.registration_number,
                'type_property': movement.aircraft.type_property.type_property if movement.aircraft.type_property else '',
                'since_date': movement.date.isoformat(),
                'movement_id': movement.id
            })

    return mpd_map


def get_crews_for_month(year: int, month: int, mpd_id: Optional[int] = None) -> QuerySet[FlightCrew]:
    """
    Возвращает список экипажей за указанный месяц с подгрузкой связанных данных (включая пометки).
    """
    qs = FlightCrew.objects.filter(
        date__year=year,
        date__month=month
    ).select_related('aircraft', 'aircraft__type_property', 'mpd', 'created_by').prefetch_related('members__member', 'notes__author')

    if mpd_id:
        qs = qs.filter(mpd_id=mpd_id)

    return qs.order_by('date', 'aircraft__registration_number')


def get_mpd_crew_map(year: int, month: int) -> Dict[int, Dict[str, List[Dict[str, Any]]]]:
    """
    Формирует карту экипажей для отображения в сетке планирования:
    { mpd_id: { 'YYYY-MM-DD': [crew_dict, ...] } }
    """
    from .models import CREW_ROLES
    crews = get_crews_for_month(year, month)
    crew_map: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}
    today = timezone.now().date()
    min_editable_date = today - timedelta(days=1)
    max_editable_date = today + timedelta(days=1)
    roles_dict = dict(CREW_ROLES)

    for crew in crews:
        mpd_id = crew.mpd_id
        date_str = crew.date.isoformat()

        if mpd_id not in crew_map:
            crew_map[mpd_id] = {}
        if date_str not in crew_map[mpd_id]:
            crew_map[mpd_id][date_str] = []

        members_list = [
            {
                'member_id': m.member_id,
                'name': m.member.title or m.member.username,
                'role': m.role,
                'role_label': m.get_role_display(),
            }
            for m in crew.members.all()
        ]

        notes_list = [
            {
                'id': n.id,
                'author_id': n.author_id,
                'author_name': n.author.title if (n.author and n.author.title) else (n.author.username if n.author else 'Неизвестно'),
                'author_role': n.author_role,
                'author_role_label': roles_dict.get(n.author_role, n.author_role),
                'message': n.message,
                'created_at': n.created_at.strftime('%d.%m.%Y %H:%M'),
                'created_at_time': n.created_at.strftime('%H:%M')
            }
            for n in crew.notes.all()
        ]

        latest_note = notes_list[0] if notes_list else None
        can_add_note = (min_editable_date <= crew.date <= max_editable_date)

        crew_map[mpd_id][date_str].append({
            'id': crew.id,
            'aircraft_id': crew.aircraft_id,
            'aircraft_number': crew.aircraft.registration_number if crew.aircraft else 'Резерв',
            'aircraft_type': crew.aircraft.type_property.type_property if (crew.aircraft and crew.aircraft.type_property) else '',
            'flight_type': crew.flight_type,
            'flight_type_label': crew.get_flight_type_display(),
            'name': crew.name,
            'comment': crew.comment,
            'members': members_list,
            'notes': notes_list,
            'latest_note': latest_note,
            'can_add_note': can_add_note
        })

    return crew_map



def get_available_aircraft_for_mpd(mpd_id: int, target_date: Optional[date] = None) -> List[Estate]:
    """
    Возвращает список воздушных судов, находящихся на указанном МПД на дату target_date.
    """
    if target_date is None:
        target_date = timezone.now().date()

    mpd_map = get_mpd_aircraft_map(target_date)
    aircraft_info_list = mpd_map.get(mpd_id, [])
    aircraft_ids = [info['aircraft_id'] for info in aircraft_info_list]

    return list(Estate.objects.filter(id__in=aircraft_ids).select_related('type_property').order_by('registration_number'))
