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


def get_personnel_utilization_report_data(year: int, month: int, job_category: Optional[str] = None) -> Dict[str, Any]:
    """
    Формирует структурированный аналитический отчет по загрузке летного состава за выбранный месяц
    с разделением на 4 ключевые авиационно-кадровые группы:
    1. Оперативный резерв и нераспределенный состав (Загрузка 0%)
    2. Минимальная производственная нагрузка (Загрузка 1–30% / 1–9 дней)
    3. Штатная производственная загрузка (Загрузка 31–70% / 10–20 дней)
    4. Интенсивная летная нагрузка / Контроль утомляемости (Загрузка свыше 70% / 21+ день)
    """
    from customers_app.models import DataBaseUser
    from .models import CREW_ROLES

    ALLOWED_JOBS = ['командир', 'пилот', 'бортмеханик', 'Командир', 'Бортмеханик', 'инструктор', 'Бортовой']
    MONTH_NAMES_RU = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    total_month_days = (last_day - first_day).days + 1

    # Загружаем летный состав
    q_conditions = Q()
    for keyword in ALLOWED_JOBS:
        q_conditions |= Q(user_work_profile__job__name__icontains=keyword)

    pilots_qs = DataBaseUser.objects.filter(
        is_active=True,
        user_work_profile__isnull=False
    ).filter(q_conditions).select_related('user_work_profile__job', 'user_work_profile__divisions').order_by('last_name', 'first_name').distinct()

    # Загружаем все назначения за месяц
    assignments = PilotAssignment.objects.filter(
        date__year=year,
        date__month=month
    ).select_related('pilot', 'mpd', 'crew', 'crew__aircraft', 'crew__aircraft__type_property')

    pilot_assignments_map: Dict[int, List[PilotAssignment]] = {}
    for a in assignments:
        if a.pilot_id not in pilot_assignments_map:
            pilot_assignments_map[a.pilot_id] = []
        pilot_assignments_map[a.pilot_id].append(a)

    roles_dict = dict(CREW_ROLES)
    pilots_stats = []

    for pilot in pilots_qs:
        p_assigns = pilot_assignments_map.get(pilot.id, [])
        assigned_days = len(p_assigns)
        free_days = max(0, total_month_days - assigned_days)
        utilization_pct = round((assigned_days / total_month_days) * 100, 1) if total_month_days > 0 else 0.0

        mpd_counts = {}
        aircraft_set = set()
        roles_set = set()
        check_flights_count = 0

        for a in p_assigns:
            if a.mpd:
                mpd_counts[a.mpd.name] = mpd_counts.get(a.mpd.name, 0) + 1
            if a.crew:
                if a.crew.aircraft:
                    aircraft_set.add(a.crew.aircraft.registration_number)
                else:
                    aircraft_set.add('Резерв')
                if a.crew.flight_type in ['check_flight_engineer', 'check_pilot', 'double_check']:
                    check_flights_count += 1
            if a.role_in_crew:
                roles_set.add(roles_dict.get(a.role_in_crew, a.role_in_crew))

        mpd_summary = ", ".join([f"{name} ({cnt} дн.)" for name, cnt in mpd_counts.items()]) if mpd_counts else "—"
        aircraft_summary = ", ".join(sorted(aircraft_set)) if aircraft_set else "—"
        roles_summary = ", ".join(sorted(roles_set)) if roles_set else ("Вне экипажа" if assigned_days > 0 else "—")

        job_name = pilot.user_work_profile.job.name if (hasattr(pilot, 'user_work_profile') and pilot.user_work_profile and pilot.user_work_profile.job) else "Должность не указана"
        department_name = pilot.user_work_profile.divisions.name if (hasattr(pilot, 'user_work_profile') and pilot.user_work_profile and pilot.user_work_profile.divisions) else "Летная служба"

        # Фильтрация по выбранной категории должности
        if job_category:
            job_lower = job_name.lower()
            if job_category == 'commander' and not any(k in job_lower for k in ['командир воздушного судна', 'командир летного']):
                continue
            elif job_category == 'copilot' and 'второй пилот' not in job_lower:
                continue
            elif job_category == 'flight_engineer' and not any(k in job_lower for k in ['бортмеханик', 'бортовой механик', 'старший бортмеханик']):
                continue
            elif job_category == 'instructor' and 'инструктор' not in job_lower:
                continue

        pilots_stats.append({
            'pilot_id': pilot.id,
            'full_name': pilot.get_full_name() or pilot.title or pilot.username,
            'fio': pilot.title or pilot.username,
            'job': job_name,
            'department': department_name,
            'assigned_days': assigned_days,
            'free_days': free_days,
            'utilization_percent': utilization_pct,
            'mpd_summary': mpd_summary,
            'aircraft_summary': aircraft_summary,
            'roles_summary': roles_summary,
            'check_flights_count': check_flights_count,
        })

    # Разбивка на 4 группы
    g1_idle = [p for p in pilots_stats if p['assigned_days'] == 0]
    g2_low = [p for p in pilots_stats if 0 < p['assigned_days'] <= 9]
    g3_optimal = [p for p in pilots_stats if 10 <= p['assigned_days'] <= 20]
    g4_high = [p for p in pilots_stats if p['assigned_days'] >= 21]

    total_pilots = len(pilots_stats)
    total_man_days = sum(p['assigned_days'] for p in pilots_stats)
    avg_utilization = round(sum(p['utilization_percent'] for p in pilots_stats) / total_pilots, 1) if total_pilots > 0 else 0.0

    return {
        'year': year,
        'month': month,
        'month_name': f"{MONTH_NAMES_RU[month]} {year}",
        'month_name_simple': MONTH_NAMES_RU[month],
        'total_month_days': total_month_days,
        'total_pilots': total_pilots,
        'total_man_days': total_man_days,
        'avg_utilization': avg_utilization,
        'job_category': job_category or '',
        'groups': [
            {
                'id': 'group_1',
                'title': 'Оперативный резерв и нераспределенный состав',
                'subtitle': 'Сотрудники без летных назначений в отчетном месяце',
                'badge': 'Загрузка 0% (0 дн.)',
                'description': 'Летный состав в оперативном резерве базы, отпусках, на переподготовке или не задействованный на МПД.',
                'class_name': 'idle',
                'color': 'secondary',
                'border_color': '#94a3b8',
                'bg_light': '#f8fafc',
                'pilots': g1_idle,
                'count': len(g1_idle),
                'share_percent': round((len(g1_idle) / total_pilots) * 100, 1) if total_pilots > 0 else 0.0
            },
            {
                'id': 'group_2',
                'title': 'Минимальная производственная нагрузка',
                'subtitle': 'Частичная занятость / Подмены',
                'badge': 'Загрузка 1%–30% (1–9 дн.)',
                'description': 'Сотрудники с эпизодической или низкой производственной нагрузкой.',
                'class_name': 'low',
                'color': 'info',
                'border_color': '#38bdf8',
                'bg_light': '#f0f9ff',
                'pilots': g2_low,
                'count': len(g2_low),
                'share_percent': round((len(g2_low) / total_pilots) * 100, 1) if total_pilots > 0 else 0.0
            },
            {
                'id': 'group_3',
                'title': 'Штатная производственная загрузка',
                'subtitle': 'Оптимальный баланс летного времени',
                'badge': 'Загрузка 31%–70% (10–20 дн.)',
                'description': 'Нормативная плановая нагрузка, соответствующая типовому графику смен и межполетного отдыха.',
                'class_name': 'optimal',
                'color': 'success',
                'border_color': '#4ade80',
                'bg_light': '#f0fdf4',
                'pilots': g3_optimal,
                'count': len(g3_optimal),
                'share_percent': round((len(g3_optimal) / total_pilots) * 100, 1) if total_pilots > 0 else 0.0
            },
            {
                'id': 'group_4',
                'title': 'Интенсивная летная нагрузка (Контроль утомляемости)',
                'subtitle': 'Повышенная занятость / Приоритетный контроль норм отдыха',
                'badge': 'Загрузка свыше 70% (21+ дн.)',
                'description': 'Высокая интенсивность полетов. Требуется приоритетный контроль норм рабочего времени и отдыха.',
                'class_name': 'high',
                'color': 'danger',
                'border_color': '#f87171',
                'bg_light': '#fef2f2',
                'pilots': g4_high,
                'count': len(g4_high),
                'share_percent': round((len(g4_high) / total_pilots) * 100, 1) if total_pilots > 0 else 0.0
            }
        ]
    }


def get_aircraft_basing_report_data(
    target_date: Optional[date] = None,
    mpd_id: Optional[int] = None,
    aircraft_type_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Формирует структурированные данные официального отчета
    «БАЗИРОВАНИЕ ВС НА [Дата] год».

    Логика расчета:
    1. Определяет все активные воздушные суда (Estate), не выведенные из эксплуатации на target_date.
    2. Для каждого борта находит последнее актуальное перемещение/базирование (AircraftMovement) на дату <= target_date.
    3. Группирует воздушные суда по МПД (PlaceProductionActivity).
    4. Нумерует группы МПД и упорядочивает ВС внутри группы (по типу ВС и бортовому номеру).
    5. Вычисляет сводные статистические показатели (общее число ВС на базировании, распределение по типам, количество ВС в резерве).
    """
    if target_date is None:
        target_date = timezone.now().date()

    # 1. Получаем все активные воздушные суда (не списанные к выбранной дате)
    active_aircraft_qs = Estate.objects.filter(
        Q(decommission_date__isnull=True) | Q(decommission_date__gt=target_date)
    ).select_related('type_property').order_by('type_property__type_property', 'registration_number')

    if aircraft_type_id:
        active_aircraft_qs = active_aircraft_qs.filter(type_property_id=aircraft_type_id)

    active_aircraft_map = {ac.id: ac for ac in active_aircraft_qs}
    active_aircraft_ids = set(active_aircraft_map.keys())

    if not active_aircraft_ids:
        return {
            'target_date': target_date,
            'target_date_formatted': target_date.strftime('%d.%m.%Y'),
            'target_date_short': target_date.strftime('%d.%m.%y'),
            'target_date_year': target_date.year,
            'mpd_groups': [],
            'unassigned_aircrafts': [],
            'total_aircrafts': 0,
            'total_mpds': 0,
            'total_reserve': 0,
            'type_counts': [],
        }

    # 2. Получаем все перемещения на дату <= target_date для активных ВС
    movements = AircraftMovement.objects.filter(
        date__lte=target_date,
        aircraft_id__in=active_aircraft_ids
    ).select_related(
        'aircraft', 'aircraft__type_property', 'mpd', 'created_by'
    ).order_by('aircraft_id', '-date', '-created_at')

    # Находим последнее актуальное перемещение для каждого борта
    latest_movements: Dict[int, AircraftMovement] = {}
    for m in movements:
        if m.aircraft_id not in latest_movements:
            latest_movements[m.aircraft_id] = m

    # 3. Группируем по МПД
    mpd_groups_dict: Dict[int, Dict[str, Any]] = {}
    unassigned_aircrafts: List[Dict[str, Any]] = []
    total_reserve = 0
    type_counter: Dict[str, int] = {}

    for ac_id, ac in active_aircraft_map.items():
        type_title = ac.type_property.type_property if ac.type_property else "Без типа"
        latest_m = latest_movements.get(ac_id)

        if latest_m and latest_m.mpd:
            current_mpd = latest_m.mpd
            if mpd_id and current_mpd.id != mpd_id:
                continue

            if current_mpd.id not in mpd_groups_dict:
                mpd_groups_dict[current_mpd.id] = {
                    'mpd': current_mpd,
                    'mpd_id': current_mpd.id,
                    'mpd_name': current_mpd.name,
                    'mpd_short_name': current_mpd.short_name or current_mpd.name,
                    'aircrafts': []
                }

            comment_text = (latest_m.comment or "").strip()
            is_reserve = bool("резерв" in comment_text.lower())
            if is_reserve:
                total_reserve += 1

            type_counter[type_title] = type_counter.get(type_title, 0) + 1

            mpd_groups_dict[current_mpd.id]['aircrafts'].append({
                'aircraft_id': ac.id,
                'registration_number': ac.registration_number,
                'type_name': type_title,
                'type_property_id': ac.type_property_id if ac.type_property else None,
                'arrival_date': latest_m.date,
                'arrival_date_formatted': latest_m.date.strftime('%d.%m.%y'),
                'arrival_date_full': latest_m.date.strftime('%d.%m.%Y'),
                'comment': comment_text,
                'is_reserve': is_reserve,
                'movement_id': latest_m.id,
                'created_by': (
                    latest_m.created_by.title
                    if (latest_m.created_by and latest_m.created_by.title)
                    else (latest_m.created_by.username if latest_m.created_by else "")
                ),
            })
        else:
            # Борт без зафиксированного перемещения на дату
            if not mpd_id:
                unassigned_aircrafts.append({
                    'aircraft_id': ac.id,
                    'registration_number': ac.registration_number,
                    'type_name': type_title,
                    'type_property_id': ac.type_property_id if ac.type_property else None,
                    'arrival_date': None,
                    'arrival_date_formatted': "—",
                    'arrival_date_full': "—",
                    'comment': "Дислокация не зафиксирована",
                    'is_reserve': False,
                    'movement_id': None,
                })

    # Сортируем группы МПД по наименованию
    sorted_mpd_groups = sorted(mpd_groups_dict.values(), key=lambda g: g['mpd_name'].upper())

    # Сортируем ВС внутри групп и присваиваем порядковые номера 1., 2., 3...
    total_based_aircrafts = 0
    for idx, group in enumerate(sorted_mpd_groups, start=1):
        group['index'] = idx
        # Сортировка ВС внутри МПД: по типу ВС, затем по рег. номеру
        group['aircrafts'] = sorted(
            group['aircrafts'],
            key=lambda x: (x['type_name'], x['registration_number'])
        )
        group['aircraft_count'] = len(group['aircrafts'])
        total_based_aircrafts += group['aircraft_count']

    # Сортировка распределения по типам ВС
    type_counts = [
        {'type_name': t_name, 'count': cnt}
        for t_name, cnt in sorted(type_counter.items(), key=lambda x: (-x[1], x[0]))
    ]

    return {
        'target_date': target_date,
        'target_date_formatted': target_date.strftime('%d.%m.%Y'),
        'target_date_short': target_date.strftime('%d.%m.%y'),
        'target_date_year': target_date.year,
        'mpd_groups': sorted_mpd_groups,
        'unassigned_aircrafts': unassigned_aircrafts,
        'total_aircrafts': total_based_aircrafts,
        'total_mpds': len(sorted_mpd_groups),
        'total_reserve': total_reserve,
        'type_counts': type_counts,
    }



