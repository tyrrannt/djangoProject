# flight_planning/services.py
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from .models import PilotAssignment, AircraftMovement


def record_aircraft_movement(
    aircraft_id: int,
    mpd_id: int,
    movement_date: date,
    created_by=None,
    comment: str = ""
) -> AircraftMovement:
    """
    Регистрирует перемещение/базирование воздушного судна на МПД.

    Args:
        aircraft_id: ID воздушного судна (Estate).
        mpd_id: ID места производственной деятельности (PlaceProductionActivity).
        movement_date: Дата перемещения / начала базирования.
        created_by: Пользователь (DataBaseUser), зафиксировавший перемещение.
        comment: Примечание или основание для перемещения.

    Returns:
        Созданный объект AircraftMovement.
    """
    return AircraftMovement.objects.create(
        aircraft_id=aircraft_id,
        mpd_id=mpd_id,
        date=movement_date,
        created_by=created_by,
        comment=comment
    )

def format_short_name(full_name: str) -> str:
    parts = full_name.split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name

def get_grouped_pilot_schedule(assignments: List[PilotAssignment], year: int, month: int) -> List[Dict[str, Any]]:
    if not assignments and not (year and month):
        return []

    # Определяем границы месяца
    start_of_month = date(year, month, 1)
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

    # Pre-fetch all assignments for the month to build the crew mapping
    from collections import defaultdict
    all_month_assignments = PilotAssignment.objects.filter(
        date__gte=start_of_month,
        date__lte=end_of_month
    ).select_related('pilot')
    
    crew_lookup = defaultdict(lambda: defaultdict(set))
    for a in all_month_assignments:
        name = a.pilot.title or a.pilot.username
        crew_lookup[a.date][a.mpd_id].add(format_short_name(name))

    # Создаем карту назначений для быстрого доступа
    assignment_map = {a.date: a for a in assignments}

    grouped_schedule = []
    current_date = start_of_month
    
    range_start = start_of_month
    current_mpd_id = None
    current_mpd_name = None
    
    # Инициализация первого дня
    first_assignment = assignment_map.get(current_date)
    if first_assignment:
        current_mpd_id = first_assignment.mpd_id
        current_mpd_name = first_assignment.mpd.name
    else:
        current_mpd_id = None
        current_mpd_name = "Пропуск"

    while current_date <= end_of_month:
        next_date = current_date + timedelta(days=1)
        next_assignment = assignment_map.get(next_date) if next_date <= end_of_month else None
        
        next_mpd_id = next_assignment.mpd_id if next_assignment else None
        next_mpd_name = next_assignment.mpd.name if next_assignment else "Пропуск"
        
        # Если следующий день имеет другой МПД (или это конец месяца), закрываем текущий диапазон
        if next_date > end_of_month or next_mpd_id != current_mpd_id:
            range_crew = set()
            if current_mpd_id is not None:
                d = range_start
                while d <= current_date:
                    range_crew.update(crew_lookup[d][current_mpd_id])
                    d += timedelta(days=1)

            grouped_schedule.append({
                'start_date': range_start,
                'end_date': current_date,
                'mpd_name': current_mpd_name,
                'is_gap': current_mpd_id is None,
                'days_count': (current_date - range_start).days + 1,
                'crew': sorted(list(range_crew))
            })
            
            # Начинаем новый диапазон
            range_start = next_date
            current_mpd_id = next_mpd_id
            current_mpd_name = next_mpd_name

        current_date = next_date

    return grouped_schedule


def validate_crew_composition(flight_type: str, members: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Проверяет соответствие состава экипажа правилам формирования:
    - Обычный полет: минимум 3 человека (КВС, Второй пилот/КВС/инструктор, Бортмеханик/инструктор).
    - Проверочный полет бортмеханика: КВС, Второй пилот/КВС/инструктор, и ОБЯЗАТЕЛЬНО оба: Бортмеханик И Бортмеханик-инструктор (мин. 4 чел).
    - Проверочный полет пилотов: КВС, Инструктор (проверяющий), Бортмеханик/инструктор (+ опционально 2-й пилот/КВС).
    - Двойной проверочный полет: Состав пилотов с инструктором + ОБЯЗАТЕЛЬНО оба: Бортмеханик И Бортмеханик-инструктор (мин. 4 чел).
    """
    errors = []
    if not members:
        return False, ["Экипаж не может быть пустым."]

    member_ids = [m.get('member_id') or m.get('pilot_id') for m in members]
    if len(member_ids) != len(set(member_ids)):
        errors.append("Один и тот же сотрудник не может занимать несколько ролей в одном экипаже.")

    roles = [m.get('role') for m in members]
    commanders_count = roles.count('commander')
    copilots_count = roles.count('copilot')
    pilot_instructors_count = roles.count('pilot_instructor')
    flight_engineers_count = roles.count('flight_engineer')
    fe_instructors_count = roles.count('flight_engineer_instructor')

    total_pilots = commanders_count + copilots_count + pilot_instructors_count
    total_engineers = flight_engineers_count + fe_instructors_count

    if flight_type == 'standard':
        if commanders_count < 1:
            errors.append("В экипаже обязательно должен быть назначен Командир воздушного судна (КВС).")
        if total_pilots < 2:
            errors.append("В экипаже должен быть второй пилот (либо второй КВС, либо пилот-инструктор).")
        if total_engineers < 1:
            errors.append("В экипаже обязательно должен быть Бортмеханик (или бортмеханик-инструктор).")
        if len(members) < 3:
            errors.append("Минимальный состав экипажа для обычного полета — 3 человека (КВС, 2-й пилот, бортмеханик).")

    elif flight_type == 'check_flight_engineer':
        if commanders_count < 1:
            errors.append("В экипаже обязательно должен быть КВС.")
        if total_pilots < 2:
            errors.append("В экипаже должен быть второй пилот (либо второй КВС, либо пилот-инструктор).")
        if flight_engineers_count < 1:
            errors.append("При проверке бортмеханика обязательно должен быть проверяемый Бортмеханик.")
        if fe_instructors_count < 1:
            errors.append("При проверке бортмеханика обязательно должен присутствовать Бортмеханик-инструктор (проверяющий).")
        if len(members) < 4:
            errors.append("Состав экипажа при проверке бортмеханика должен быть не менее 4 человек.")

    elif flight_type == 'check_pilot':
        if commanders_count < 1:
            errors.append("В экипаже обязательно должен быть КВС.")
        if pilot_instructors_count < 1:
            errors.append("При проверочном полете пилотов обязательно должен присутствовать Пилот-инструктор (проверяющий).")
        if total_engineers < 1:
            errors.append("В экипаже обязательно должен быть Бортмеханик (или бортмеханик-инструктор).")
        if len(members) < 3:
            errors.append("Минимальный состав экипажа для проверки пилотов — 3 человека.")

    elif flight_type == 'double_check':
        if commanders_count < 1:
            errors.append("В экипаже обязательно должен быть КВС.")
        if pilot_instructors_count < 1:
            errors.append("При двойном проверочном полете обязательно должен присутствовать Пилот-инструктор.")
        if flight_engineers_count < 1:
            errors.append("При двойном проверочном полете обязательно должен быть проверяемый Бортмеханик.")
        if fe_instructors_count < 1:
            errors.append("При двойном проверочном полете обязательно должен присутствовать Бортмеханик-инструктор.")
        if len(members) < 4:
            errors.append("Минимальный состав экипажа при двойной проверке — не менее 4 человек.")

    return len(errors) == 0, errors


def check_crew_member_conflicts(
    mpd_id: int,
    start_date: date,
    end_date: date,
    members: List[Dict[str, Any]],
    current_crew_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Проверяет занятость участников экипажа на других МПД или в других экипажах в указанный диапазон дат.
    Возвращает список конфликтов с детальной информацией.
    """
    from .models import PilotAssignment
    conflicts = []
    member_ids = [m['member_id'] for m in members if 'member_id' in m]

    if not member_ids:
        return conflicts

    assignments = PilotAssignment.objects.filter(
        pilot_id__in=member_ids,
        date__gte=start_date,
        date__lte=end_date
    ).select_related('pilot', 'mpd', 'crew', 'crew__aircraft')

    for a in assignments:
        pilot_name = a.pilot.title or a.pilot.username
        date_str = a.date.isoformat()
        date_fmt = a.date.strftime('%d.%m.%Y')

        # 1. Назначен на ДРУГОЕ МПД
        if a.mpd_id != mpd_id:
            crew_info = ""
            if a.crew:
                crew_reg = a.crew.aircraft.registration_number if a.crew.aircraft else "Резерв"
                crew_info = f", в составе экипажа {crew_reg}"
            conflicts.append({
                'member_id': a.pilot_id,
                'pilot_name': pilot_name,
                'date': date_str,
                'date_formatted': date_fmt,
                'assignment_id': a.id,
                'old_mpd_id': a.mpd_id,
                'old_mpd_name': a.mpd.name,
                'old_crew_id': a.crew_id,
                'old_crew_name': a.crew.aircraft.registration_number if (a.crew and a.crew.aircraft) else ('Резерв' if a.crew else ''),
                'description': f"{pilot_name}: {date_fmt} уже назначен на МПД «{a.mpd.name}»{crew_info}."
            })
        # 2. На том же МПД, но в ДРУГОМ экипаже (и это не редактируемый экипаж)
        elif a.crew_id and (current_crew_id is None or a.crew_id != current_crew_id):
            crew_reg = a.crew.aircraft.registration_number if a.crew.aircraft else "Резерв"
            conflicts.append({
                'member_id': a.pilot_id,
                'pilot_name': pilot_name,
                'date': date_str,
                'date_formatted': date_fmt,
                'assignment_id': a.id,
                'old_mpd_id': a.mpd_id,
                'old_mpd_name': a.mpd.name,
                'old_crew_id': a.crew_id,
                'old_crew_name': crew_reg,
                'description': f"{pilot_name}: {date_fmt} уже состоит в другом экипаже ({crew_reg}) на этом же МПД."
            })

    return conflicts


def create_or_update_flight_crew_range(
    mpd_id: int,
    aircraft_id: Optional[int],
    start_date: date,
    end_date: date,
    flight_type: str,
    members: List[Dict[str, Any]],
    created_by=None,
    comment: str = "",
    crew_name: str = "",
    force_override: bool = False
) -> Dict[str, Any]:
    """
    Создает или обновляет летный экипаж на диапазон дат.
    Атомарно привязывает участников к экипажу и синхронизирует PilotAssignment.
    """
    is_valid, errors = validate_crew_composition(flight_type, members)
    if not is_valid:
        return {'status': 'error', 'errors': errors}

    from django.db import transaction
    from .models import FlightCrew, CrewMember, PilotAssignment
    from hrdepartment_app.models import PlaceProductionActivity
    from contracts_app.models import Estate

    try:
        mpd = PlaceProductionActivity.objects.get(id=mpd_id)
    except PlaceProductionActivity.DoesNotExist:
        return {'status': 'error', 'errors': ['МПД не найдено.']}

    aircraft = Estate.objects.filter(id=aircraft_id).first() if aircraft_id else None

    # 1. Проверка конфликтов воздушного судна
    aircraft_conflicts = []
    current = start_date
    while current <= end_date:
        if aircraft:
            existing_aircraft_crews = FlightCrew.objects.filter(
                aircraft=aircraft,
                date=current
            )
            for ex in existing_aircraft_crews:
                if ex.mpd_id != mpd_id:
                    aircraft_conflicts.append(
                        f"Борт {aircraft.registration_number} на дату {current.strftime('%d.%m.%Y')} уже закреплен за экипажем на {ex.mpd.name}."
                    )
        current += timedelta(days=1)

    if aircraft_conflicts:
        return {'status': 'conflict', 'conflict_type': 'aircraft', 'errors': aircraft_conflicts, 'can_override': False}

    # 2. Проверка конфликтов занятости членов экипажа на других МПД / экипажах
    member_conflicts = check_crew_member_conflicts(
        mpd_id=mpd_id,
        start_date=start_date,
        end_date=end_date,
        members=members
    )

    if member_conflicts and not force_override:
        return {
            'status': 'conflict',
            'conflict_type': 'members',
            'conflicts': member_conflicts,
            'can_override': True,
            'errors': [c['description'] for c in member_conflicts]
        }

    created_crews = []
    with transaction.atomic():
        current = start_date
        while current <= end_date:
            # Ищем существующий экипаж
            crew_qs = FlightCrew.objects.filter(mpd=mpd, date=current)
            if aircraft:
                crew_obj = crew_qs.filter(aircraft=aircraft).first()
            else:
                crew_obj = crew_qs.filter(aircraft__isnull=True, name=crew_name).first()

            if not crew_obj:
                crew_obj = FlightCrew.objects.create(
                    mpd=mpd,
                    aircraft=aircraft,
                    date=current,
                    flight_type=flight_type,
                    name=crew_name,
                    comment=comment,
                    created_by=created_by
                )
            else:
                crew_obj.flight_type = flight_type
                crew_obj.aircraft = aircraft
                crew_obj.name = crew_name
                crew_obj.comment = comment
                crew_obj.save()

            # Удаляем старых участников, не вошедших в новый состав
            old_member_ids = set(crew_obj.members.values_list('member_id', flat=True))
            new_member_ids = set([m['member_id'] for m in members])

            removed_ids = old_member_ids - new_member_ids
            if removed_ids:
                CrewMember.objects.filter(crew=crew_obj, member_id__in=removed_ids).delete()
                PilotAssignment.objects.filter(crew=crew_obj, pilot_id__in=removed_ids, date=current).update(
                    crew=None, role_in_crew=""
                )

            # Сохраняем новых участников и обновляем PilotAssignment
            for m in members:
                member_id = m['member_id']
                role = m['role']

                # Если был в другом экипаже на эту дату, удаляем его из старого экипажа
                old_crews = FlightCrew.objects.filter(
                    date=current,
                    members__member_id=member_id
                ).exclude(id=crew_obj.id)
                for oc in old_crews:
                    CrewMember.objects.filter(crew=oc, member_id=member_id).delete()

                CrewMember.objects.update_or_create(
                    crew=crew_obj,
                    member_id=member_id,
                    defaults={'role': role}
                )

                assignment, created = PilotAssignment.objects.get_or_create(
                    pilot_id=member_id,
                    date=current,
                    defaults={
                        'mpd': mpd,
                        'crew': crew_obj,
                        'role_in_crew': role,
                        'created_by': created_by
                    }
                )
                if not created:
                    assignment.mpd = mpd
                    assignment.crew = crew_obj
                    assignment.role_in_crew = role
                    assignment.save()

            created_crews.append(crew_obj.id)
            current += timedelta(days=1)

    return {
        'status': 'success',
        'created_crews_count': len(created_crews),
        'mpd_id': mpd_id,
        'aircraft_id': aircraft_id,
        'aircraft_name': aircraft.registration_number if aircraft else 'Резерв'
    }


def update_flight_crew(
    crew_id: int,
    mpd_id: int,
    aircraft_id: Optional[int],
    target_date: date,
    flight_type: str,
    members: List[Dict[str, Any]],
    comment: str = "",
    crew_name: str = "",
    force_override: bool = False
) -> Dict[str, Any]:
    """
    Обновляет конкретный существующий экипаж, его участников и привязки назначений.
    """
    is_valid, errors = validate_crew_composition(flight_type, members)
    if not is_valid:
        return {'status': 'error', 'errors': errors}

    from django.db import transaction
    from .models import FlightCrew, CrewMember, PilotAssignment
    from hrdepartment_app.models import PlaceProductionActivity
    from contracts_app.models import Estate

    try:
        crew_obj = FlightCrew.objects.get(id=crew_id)
    except FlightCrew.DoesNotExist:
        return {'status': 'error', 'errors': ['Экипаж не найден.']}

    try:
        mpd = PlaceProductionActivity.objects.get(id=mpd_id)
    except PlaceProductionActivity.DoesNotExist:
        return {'status': 'error', 'errors': ['МПД не найдено.']}

    aircraft = Estate.objects.filter(id=aircraft_id).first() if aircraft_id else None

    # Проверка конфликта борта: за бортом на эту дату не должен быть закреплен ДРУГОЙ экипаж
    if aircraft:
        other_crew = FlightCrew.objects.filter(aircraft=aircraft, date=target_date).exclude(id=crew_id).first()
        if other_crew:
            return {
                'status': 'conflict',
                'conflict_type': 'aircraft',
                'can_override': False,
                'errors': [f"Борт {aircraft.registration_number} на дату {target_date.strftime('%d.%m.%Y')} уже закреплен за другим экипажем на {other_crew.mpd.name}."]
            }

    # Проверка конфликтов членов экипажа на других МПД / экипажах
    member_conflicts = check_crew_member_conflicts(
        mpd_id=mpd_id,
        start_date=target_date,
        end_date=target_date,
        members=members,
        current_crew_id=crew_id
    )

    if member_conflicts and not force_override:
        return {
            'status': 'conflict',
            'conflict_type': 'members',
            'conflicts': member_conflicts,
            'can_override': True,
            'errors': [c['description'] for c in member_conflicts]
        }

    with transaction.atomic():
        old_date = crew_obj.date
        old_member_ids = set(crew_obj.members.values_list('member_id', flat=True))
        new_member_ids = set([m['member_id'] for m in members])

        crew_obj.mpd = mpd
        crew_obj.aircraft = aircraft
        crew_obj.date = target_date
        crew_obj.flight_type = flight_type
        crew_obj.name = crew_name
        crew_obj.comment = comment
        crew_obj.save()

        # Если дата изменилась или участники удалены, отвязываем старые назначения
        if old_date != target_date:
            PilotAssignment.objects.filter(crew=crew_obj, date=old_date).update(crew=None, role_in_crew="")
        else:
            removed_ids = old_member_ids - new_member_ids
            if removed_ids:
                CrewMember.objects.filter(crew=crew_obj, member_id__in=removed_ids).delete()
                PilotAssignment.objects.filter(crew=crew_obj, pilot_id__in=removed_ids, date=target_date).update(
                    crew=None, role_in_crew=""
                )

        # Сохраняем участников и обновляем PilotAssignment
        for m in members:
            member_id = m['member_id']
            role = m['role']

            # Если состоял в другом экипаже на эту дату, удаляем
            old_crews = FlightCrew.objects.filter(
                date=target_date,
                members__member_id=member_id
            ).exclude(id=crew_obj.id)
            for oc in old_crews:
                CrewMember.objects.filter(crew=oc, member_id=member_id).delete()

            CrewMember.objects.update_or_create(
                crew=crew_obj,
                member_id=member_id,
                defaults={'role': role}
            )

            assignment, created = PilotAssignment.objects.get_or_create(
                pilot_id=member_id,
                date=target_date,
                defaults={
                    'mpd': mpd,
                    'crew': crew_obj,
                    'role_in_crew': role,
                }
            )
            if not created:
                assignment.mpd = mpd
                assignment.crew = crew_obj
                assignment.role_in_crew = role
                assignment.save()

    return {
        'status': 'success',
        'crew_id': crew_obj.id,
        'mpd_id': mpd_id,
        'aircraft_id': aircraft_id,
        'aircraft_name': aircraft.registration_number if aircraft else 'Резерв'
    }



def delete_flight_crew(crew_id: int) -> bool:
    """
    Удаляет экипаж и отвязывает связанные назначения PilotAssignment.
    """
    from .models import FlightCrew, PilotAssignment
    try:
        crew = FlightCrew.objects.get(id=crew_id)
        PilotAssignment.objects.filter(crew=crew).update(crew=None, role_in_crew="")
        crew.delete()
        return True
    except FlightCrew.DoesNotExist:
        return False


