import logging
import re
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set, Sequence
from django.db.models import Q
from .models import PilotAssignment, AircraftMovement, PeriodicCheckRecord

logger = logging.getLogger(__name__)



def handle_aircraft_movement_crew_fallback(
        aircraft_id: int,
        new_mpd_id: int,
        movement_date: date
) -> Tuple[int, List[str]]:
    """
    При перемещении борта ВС на новый МПД:
    находит все запланированные экипажи с этим бортом на других МПД (на дату >= movement_date),
    и автоматически переводит их в статус «Резервный экипаж» (снимает борт: aircraft = None),
    сохраняя состав экипажа и назначения пилотов на их базах.

    Returns:
        (Количество переведенных в резерв экипажей, список названий затронутых МПД)
    """
    from .models import FlightCrew
    from contracts_app.models import Estate

    aircraft = Estate.objects.filter(id=aircraft_id).first()
    if not aircraft:
        return 0, []

    affected_crews = FlightCrew.objects.filter(
        aircraft_id=aircraft_id,
        date__gte=movement_date
    ).exclude(mpd_id=new_mpd_id).select_related('mpd')

    count = affected_crews.count()
    if count == 0:
        return 0, []

    mpd_names = sorted(list(set(affected_crews.values_list('mpd__name', flat=True))))

    # Сбрасываем борт в резерв у всех затронутых экипажей
    for crew in affected_crews:
        crew.aircraft = None
        if not crew.name or crew.name == 'standard':
            crew.name = 'Резерв'
        crew.save()

    return count, mpd_names


def clean_empty_flight_crews(
        mpd_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
) -> int:
    """
    Удаляет экипажи-призраки (в которых не осталось ни одного члена экипажа).
    """
    from .models import FlightCrew
    qs = FlightCrew.objects.filter(members__isnull=True)
    if mpd_id:
        qs = qs.filter(mpd_id=mpd_id)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    deleted_count, _ = qs.delete()
    return deleted_count


def record_aircraft_movement(
        aircraft_id: int,
        mpd_id: int,
        movement_date: date,
        created_by=None,
        comment: str = ""
) -> AircraftMovement:
    """
    Регистрирует перемещение/базирование воздушного судна на МПД
    и автоматически переводит в Резерв экипажи с этим бортом на других МПД с даты movement_date.

    Args:
        aircraft_id: ID воздушного судна (Estate).
        mpd_id: ID места производственной деятельности (PlaceProductionActivity).
        movement_date: Дата перемещения / начала базирования.
        created_by: Пользователь (DataBaseUser), зафиксировавший перемещение.
        comment: Примечание или основание для перемещения.

    Returns:
        Созданный объект AircraftMovement.
    """
    movement = AircraftMovement.objects.create(
        aircraft_id=aircraft_id,
        mpd_id=mpd_id,
        date=movement_date,
        created_by=created_by,
        comment=comment
    )
    handle_aircraft_movement_crew_fallback(aircraft_id, mpd_id, movement_date)
    return movement


def format_short_name(full_name: str) -> str:
    parts = full_name.split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    elif len(parts) == 2:
        return f"{parts[0]} {parts[1][0]}."
    return full_name


def get_grouped_pilot_schedule(
        assignments: List[Any],
        year: int,
        month: int,
        crew_lookup: Optional[Dict[date, Dict[Any, Set[str]]]] = None
) -> List[Dict[str, Any]]:
    """Группирует подневные назначения пилота в непрерывные интервалы дежурств на МПД и периоды отдыха.

    Args:
        assignments (List[Any]): Список объектов назначений (моделей PilotAssignment или MockAssignment с датой и МПД).
        year (int): Год периода.
        month (int): Месяц периода (1-12).
        crew_lookup (Optional[Dict[date, Dict[Any, Set[str]]]], optional): Предварительно сформированная карта
            составов экипажей по датам и МПД {date: {mpd_id: {'Иванов И.И.', ...}}}. Если не передана,
            формируется автоматически на основе текущей базы PilotAssignment. Defaults to None.

    Returns:
        List[Dict[str, Any]]: Список сгруппированных диапазонов, каждый элемент содержит:
            - 'start_date' (date): Дата начала интервала.
            - 'end_date' (date): Дата окончания интервала.
            - 'mpd_name' (str): Наименование МПД или "Пропуск" для периодов отдыха.
            - 'is_gap' (bool): Флаг периода отдыха/пропуска (True если назначение на МПД отсутствует).
            - 'days_count' (int): Количество дней в интервале.
            - 'crew' (List[str]): Список членов экипажа, работавших на этом МПД в данный период.
    """
    if not assignments and not (year and month):
        return []

    # Определяем границы месяца
    start_of_month = date(year, month, 1)
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

    from collections import defaultdict
    if crew_lookup is None:
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
        current_mpd_id = getattr(first_assignment, 'mpd_id', None)
        if current_mpd_id is None and hasattr(first_assignment, 'mpd') and hasattr(first_assignment.mpd, 'id'):
            current_mpd_id = first_assignment.mpd.id
        current_mpd_name = first_assignment.mpd.name if hasattr(first_assignment, 'mpd') and hasattr(
            first_assignment.mpd, 'name') else "МПД"
    else:
        current_mpd_id = None
        current_mpd_name = "Пропуск"

    while current_date <= end_of_month:
        next_date = current_date + timedelta(days=1)
        next_assignment = assignment_map.get(next_date) if next_date <= end_of_month else None

        if next_assignment:
            next_mpd_id = getattr(next_assignment, 'mpd_id', None)
            if next_mpd_id is None and hasattr(next_assignment, 'mpd') and hasattr(next_assignment.mpd, 'id'):
                next_mpd_id = next_assignment.mpd.id
            next_mpd_name = next_assignment.mpd.name if hasattr(next_assignment, 'mpd') and hasattr(next_assignment.mpd,
                                                                                                    'name') else "МПД"
        else:
            next_mpd_id = None
            next_mpd_name = "Пропуск"

        # Если следующий день имеет другой МПД (или это конец месяца), закрываем текущий диапазон
        if next_date > end_of_month or next_mpd_id != current_mpd_id:
            range_crew = set()
            if current_mpd_id is not None:
                d = range_start
                while d <= current_date:
                    if d in crew_lookup and current_mpd_id in crew_lookup[d]:
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


def get_pilot_schedule_from_snapshot(
        snapshot_data: Dict[str, Any],
        pilot_id: int,
        year: int,
        month: int
) -> List[Dict[str, Any]]:
    """Извлекает назначения пилота из зафиксированного снимка документа и формирует сгруппированный график.

    Args:
        snapshot_data (Dict[str, Any]): Данные JSON-снимка документа расстановки экипажей.
        pilot_id (int): Идентификатор пользователя-пилота / бортмеханика.
        year (int): Год.
        month (int): Месяц (1-12).

    Returns:
        List[Dict[str, Any]]: Сгруппированный список рабочих интервалов и промежутков отдыха.
    """
    from collections import defaultdict
    from datetime import datetime

    class MockMPD:
        """Вспомогательный объект-заглушка МПД для совместимости."""

        def __init__(self, mpd_id: Any, name: str):
            self.id = mpd_id
            self.name = name

        def __str__(self):
            return self.name

    class MockAssignment:
        """Вспомогательный объект-заглушка назначения для совместимости с сервисом группировки."""

        def __init__(self, d: date, mpd_id: Any, mpd_name: str):
            self.date = d
            self.mpd_id = mpd_id
            self.mpd = MockMPD(mpd_id, mpd_name)

    grid = snapshot_data.get('grid', {})
    mpds_map = {str(m['id']): m['name'] for m in snapshot_data.get('mpds', [])}

    assignments = []
    crew_lookup = defaultdict(lambda: defaultdict(set))

    for mpd_key, dates_dict in grid.items():
        mpd_id = int(mpd_key) if str(mpd_key).isdigit() else mpd_key
        mpd_name = mpds_map.get(str(mpd_key), f"МПД #{mpd_key}")

        for date_str, crews_list in dates_dict.items():
            try:
                d_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                continue

            is_assigned = False
            for c in crews_list:
                for m in c.get('members', []):
                    m_pilot_id = m.get('pilot_id') or m.get('member_id') or m.get('id')
                    m_name = m.get('name') or m.get('pilot_name') or m.get('member_name') or ''
                    if m_name:
                        crew_lookup[d_obj][mpd_id].add(format_short_name(m_name))
                    if m_pilot_id == pilot_id:
                        is_assigned = True

            if is_assigned:
                assignments.append(MockAssignment(d_obj, mpd_id, mpd_name))

    assignments.sort(key=lambda a: a.date)
    return get_grouped_pilot_schedule(assignments, year, month, crew_lookup=crew_lookup)


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
            errors.append(
                "При проверке бортмеханика обязательно должен присутствовать Бортмеханик-инструктор (проверяющий).")
        if len(members) < 4:
            errors.append("Состав экипажа при проверке бортмеханика должен быть не менее 4 человек.")

    elif flight_type == 'check_pilot':
        if commanders_count < 1:
            errors.append("В экипаже обязательно должен быть КВС.")
        if pilot_instructors_count < 1:
            errors.append(
                "При проверочном полете пилотов обязательно должен присутствовать Пилот-инструктор (проверяющий).")
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


# ==============================================================================
# КОНФИГУРАЦИЯ СТАТУСОВ ТАБЕЛЯ УЧЕТА РАБОЧЕГО ВРЕМЕНИ (ReportCard / 1С:ЗУП)
# ==============================================================================

REPORT_CARD_STATUS_CONFIG: Dict[str, Dict[str, Any]] = {
    "2": {
        "code": "VACATION_ANNUAL",
        "name": "Ежегодный",
        "full_name": "Ежегодный отпуск",
        "abbr": "ОТ",
        "color": "#f59e0b",
        "is_blocking": True,
        "category": "vacation",
        "priority": 20,
    },
    "3": {
        "code": "VACATION_EXTRA_ANNUAL",
        "name": "Дополнительный ежегодный отпуск",
        "full_name": "Дополнительный ежегодный отпуск",
        "abbr": "ДО",
        "color": "#d97706",
        "is_blocking": True,
        "category": "vacation",
        "priority": 21,
    },
    "4": {
        "code": "VACATION_UNPAID",
        "name": "Отпуск за свой счет",
        "full_name": "Отпуск без сохранения заработной платы",
        "abbr": "БС",
        "color": "#64748b",
        "is_blocking": True,
        "category": "vacation",
        "priority": 22,
    },
    "5": {
        "code": "VACATION_STUDY",
        "name": "Дополнительный учебный отпуск (оплачиваемый)",
        "full_name": "Дополнительный учебный отпуск (оплачиваемый)",
        "abbr": "УО",
        "color": "#0284c7",
        "is_blocking": True,
        "category": "study",
        "priority": 23,
    },
    "6": {
        "code": "VACATION_CHILDCARE",
        "name": "Отпуск по уходу за ребенком",
        "full_name": "Отпуск по уходу за ребенком",
        "abbr": "ОР",
        "color": "#7c3aed",
        "is_blocking": True,
        "category": "leave",
        "priority": 24,
    },
    "7": {
        "code": "VACATION_CHERNOBYL_UNPAID",
        "name": "Дополнительный неоплачиваемый отпуск пострадавшим в аварии на ЧАЭС",
        "full_name": "Дополнительный неоплачиваемый отпуск пострадавшим на ЧАЭС",
        "abbr": "ОЧ",
        "color": "#475569",
        "is_blocking": True,
        "category": "vacation",
        "priority": 25,
    },
    "8": {
        "code": "VACATION_MATERNITY",
        "name": "Отпуск по беременности и родам",
        "full_name": "Отпуск по беременности и родам",
        "abbr": "БР",
        "color": "#db2777",
        "is_blocking": True,
        "category": "leave",
        "priority": 26,
    },
    "9": {
        "code": "VACATION_UNPAID_TK",
        "name": "Отпуск без оплаты согласно ТК РФ",
        "full_name": "Отпуск без оплаты согласно ТК РФ",
        "abbr": "БО",
        "color": "#64748b",
        "is_blocking": True,
        "category": "vacation",
        "priority": 27,
    },
    "10": {
        "code": "VACATION_EXTRA",
        "name": "Дополнительный отпуск",
        "full_name": "Дополнительный отпуск",
        "abbr": "ДО",
        "color": "#d97706",
        "is_blocking": True,
        "category": "vacation",
        "priority": 28,
    },
    "11": {
        "code": "VACATION_CHERNOBYL_PAID",
        "name": "Дополнительный оплачиваемый отпуск пострадавшим в аварии на ЧАЭС",
        "full_name": "Дополнительный оплачиваемый отпуск пострадавшим на ЧАЭС",
        "abbr": "ОЧ",
        "color": "#0284c7",
        "is_blocking": True,
        "category": "vacation",
        "priority": 29,
    },
    "12": {
        "code": "VACATION_MAIN",
        "name": "Основной",
        "full_name": "Основной отпуск",
        "abbr": "ОТ",
        "color": "#f59e0b",
        "is_blocking": True,
        "category": "vacation",
        "priority": 30,
    },
    "13": {
        "code": "MANUAL_INPUT",
        "name": "Ручной ввод",
        "full_name": "Ручной ввод табеля",
        "abbr": "РВ",
        "color": "#eab308",
        "is_blocking": False,
        "category": "manual",
        "priority": 80,
    },
    "14": {
        "code": "BUSINESS_TRIP_LOCAL",
        "name": "Служебная поездка",
        "full_name": "Служебная поездка",
        "abbr": "СП",
        "color": "#ea580c",
        "is_blocking": True,
        "category": "trip",
        "priority": 40,
    },
    "15": {
        "code": "BUSINESS_TRIP",
        "name": "Командировка",
        "full_name": "Командировка",
        "abbr": "КМ",
        "color": "#10b981",
        "is_blocking": True,
        "category": "trip",
        "priority": 41,
    },
    "16": {
        "code": "SICK_LEAVE",
        "name": "Больничный",
        "full_name": "Больничный лист",
        "abbr": "Б",
        "color": "#ef4444",
        "is_blocking": True,
        "category": "sick",
        "priority": 10,
    },
    "17": {
        "code": "MEDICAL_EXAM",
        "name": "Мед осмотр",
        "full_name": "Медицинский осмотр",
        "abbr": "МО",
        "color": "#06b6d4",
        "is_blocking": True,
        "category": "medical",
        "priority": 35,
    },
    "18": {
        "code": "VACATION_SCHEDULE",
        "name": "График отпусков",
        "full_name": "График отпусков (плановый)",
        "abbr": "ГО",
        "color": "#38bdf8",
        "is_blocking": False,
        "category": "vacation_plan",
        "priority": 70,
    },
    "19": {
        "code": "VACATION_RESORT",
        "name": "Отпуск на санаторно курортное лечение",
        "full_name": "Санаторно-курортное лечение",
        "abbr": "СК",
        "color": "#059669",
        "is_blocking": True,
        "category": "resort",
        "priority": 31,
    },
    "20": {
        "code": "DAY_OFF",
        "name": "Отгул",
        "full_name": "Отгул",
        "abbr": "В",
        "color": "#8b5cf6",
        "is_blocking": True,
        "category": "day_off",
        "priority": 50,
    },
}


def check_crew_member_conflicts(
        mpd_id: int,
        start_date: date,
        end_date: date,
        members: List[Dict[str, Any]],
        current_crew_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Проверяет занятость участников экипажа на других МПД, в других экипажах, а также особые статусы персонала (Отпуск, Больничный, Резерв, КПК, ВЛЭК).

    Args:
        mpd_id (int): Идентификатор МПД базирования.
        start_date (date): Дата начала периода проверки.
        end_date (date): Дата окончания периода проверки.
        members (List[Dict[str, Any]]): Список участников с ключами 'member_id' (или 'pilot_id') и 'role'.
        current_crew_id (Optional[int], optional): ID текущего редактируемого экипажа (исключается из проверки). Defaults to None.

    Returns:
        List[Dict[str, Any]]: Список выявленных конфликтов с подробным описанием причины и параметров.
    """
    from .models import PilotAssignment, EmployeeStatusRecord
    conflicts = []
    member_ids = [m.get('member_id') or m.get('pilot_id') for m in members if (m.get('member_id') or m.get('pilot_id'))]

    if not member_ids:
        return conflicts

    # 1. Проверка назначений в другие экипажи и на другие МПД (PilotAssignment)
    assignments = PilotAssignment.objects.filter(
        pilot_id__in=member_ids,
        date__gte=start_date,
        date__lte=end_date
    ).select_related('pilot', 'mpd', 'crew', 'crew__aircraft')

    for a in assignments:
        pilot_name = a.pilot.title or a.pilot.username
        date_str = a.date.isoformat()
        date_fmt = a.date.strftime('%d.%m.%Y')

        # 1.1. Назначен на ДРУГОЕ МПД
        if a.mpd_id != mpd_id:
            crew_info = ""
            if a.crew:
                crew_reg = a.crew.aircraft.registration_number if a.crew.aircraft else "Резерв"
                crew_info = f", в составе экипажа {crew_reg}"
            conflicts.append({
                'conflict_kind': 'assignment',
                'member_id': a.pilot_id,
                'pilot_name': pilot_name,
                'date': date_str,
                'date_formatted': date_fmt,
                'assignment_id': a.id,
                'old_mpd_id': a.mpd_id,
                'old_mpd_name': a.mpd.name,
                'old_crew_id': a.crew_id,
                'old_crew_name': a.crew.aircraft.registration_number if (a.crew and a.crew.aircraft) else (
                    'Резерв' if a.crew else ''),
                'description': f"{pilot_name}: {date_fmt} уже назначен на МПД «{a.mpd.name}»{crew_info}."
            })
        # 1.2. На том же МПД, но в ДРУГОМ экипаже (и это не редактируемый экипаж)
        elif a.crew_id and (current_crew_id is None or a.crew_id != current_crew_id):
            crew_reg = a.crew.aircraft.registration_number if a.crew.aircraft else "Резерв"
            conflicts.append({
                'conflict_kind': 'assignment',
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

    # 2. Проверка особых состояний / статусов сотрудников (Отпуск, Больничный, Резерв, КПК, ВЛЭК, Медосмотр)
    status_records = EmployeeStatusRecord.objects.filter(
        employee_id__in=member_ids,
        status_type__is_blocking=True,
        start_date__lte=end_date,
        end_date__gte=start_date
    ).select_related('employee', 'status_type')

    for sr in status_records:
        pilot_name = sr.employee.title or sr.employee.username
        doc_info = f" (док. №{sr.document_number})" if sr.document_number else ""
        period_str = f"с {sr.start_date.strftime('%d.%m.%Y')} по {sr.end_date.strftime('%d.%m.%Y')}"
        overlap_start = max(start_date, sr.start_date)

        conflicts.append({
            'conflict_kind': 'employee_status',
            'member_id': sr.employee_id,
            'pilot_name': pilot_name,
            'status_name': sr.status_type.name,
            'status_code': sr.status_type.code,
            'status_color': sr.status_type.color,
            'start_date': sr.start_date.isoformat(),
            'end_date': sr.end_date.isoformat(),
            'date': overlap_start.isoformat(),
            'date_formatted': period_str,
            'document_number': sr.document_number,
            'description': f"{pilot_name}: {period_str} находится в состоянии «{sr.status_type.name}»{doc_info}."
        })

    # 3. Проверка блокирующих записей из табеля учета рабочего времени (ReportCard / 1С:ЗУП)
    from hrdepartment_app.models import ReportCard
    blocking_rc_types = [k for k, v in REPORT_CARD_STATUS_CONFIG.items() if v.get('is_blocking')]
    rc_blocking_records = ReportCard.objects.filter(
        employee_id__in=member_ids,
        report_card_day__gte=start_date,
        report_card_day__lte=end_date,
        record_type__in=blocking_rc_types
    ).select_related('employee').prefetch_related('place_report_card')

    for rc in rc_blocking_records:
        meta = REPORT_CARD_STATUS_CONFIG.get(rc.record_type, {})
        pilot_name = rc.employee.title if rc.employee else "Сотрудник"
        status_name = meta.get('full_name', rc.get_record_type_display())
        day_str = rc.report_card_day.strftime('%d.%m.%Y')
        reason_str = f" ({rc.reason_adjustment})" if rc.reason_adjustment else ""

        mpd_info = ""
        if rc.record_type in ('14', '15'):
            places = [p.name for p in rc.place_report_card.all()]
            if places:
                mpd_info = f" на {', '.join(places)}"

        conflicts.append({
            'conflict_kind': 'employee_status',
            'member_id': rc.employee_id,
            'pilot_name': pilot_name,
            'status_name': f"[Табель 1С] {status_name}",
            'status_code': meta.get('code', 'REPORT_CARD_ABSENCE'),
            'status_color': meta.get('color', '#ef4444'),
            'start_date': rc.report_card_day.isoformat(),
            'end_date': rc.report_card_day.isoformat(),
            'date': rc.report_card_day.isoformat(),
            'date_formatted': day_str,
            'document_number': rc.doc_ref_key or "",
            'description': f"{pilot_name}: {day_str} имеет отметку в табеле 1С «{status_name}»{mpd_info}{reason_str}."
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
                # 1. Ищем существующий экипаж с этим бортом
                crew_obj = crew_qs.filter(aircraft=aircraft).first()
                if not crew_obj:
                    # 2. Если экипажа с этим бортом нет, проверяем, есть ли на эту дату резервный экипаж (без борта)
                    # Если есть резервный экипаж — переводим его на этот борт ВС
                    reserve_crew = crew_qs.filter(aircraft__isnull=True).first()
                    if reserve_crew:
                        crew_obj = reserve_crew
                        crew_obj.aircraft = aircraft
                    else:
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
                crew_obj = crew_qs.filter(aircraft__isnull=True, name=crew_name).first()
                if not crew_obj:
                    crew_obj = crew_qs.filter(aircraft__isnull=True).first()
                if not crew_obj:
                    crew_obj = FlightCrew.objects.create(
                        mpd=mpd,
                        aircraft=None,
                        date=current,
                        flight_type=flight_type,
                        name=crew_name,
                        comment=comment,
                        created_by=created_by
                    )

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

            # Автоматическая очистка экипажей-призраков, оставшихся без участников
            clean_empty_flight_crews(mpd_id=mpd.id, start_date=current, end_date=current)

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
                'errors': [
                    f"Борт {aircraft.registration_number} на дату {target_date.strftime('%d.%m.%Y')} уже закреплен за другим экипажем на {other_crew.mpd.name}."]
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

        # Очищаем любые оставшиеся пустыми экипажи
        clean_empty_flight_crews(mpd_id=mpd.id, start_date=target_date, end_date=target_date)

    return {
        'status': 'success',
        'crew_id': crew_obj.id,
        'mpd_id': mpd_id,
        'aircraft_id': aircraft_id,
        'aircraft_name': aircraft.registration_number if aircraft else 'Резерв'
    }


def batch_swap_aircraft(
        mpd_id: int,
        start_date: date,
        end_date: date,
        old_aircraft_id: Optional[Any],
        new_aircraft_id: Optional[Any],
        created_by=None
) -> Dict[str, Any]:
    """
    Выполняет пакетную замену борта ВС в экипажах на указанном МПД в заданном интервале дат.

    Поддерживает сценарии:
    - Замена конкретного борта (old_aircraft_id: int) на новый борт (new_aircraft_id: int)
    - Перевод экипажей конкретного борта в Резерв (new_aircraft_id: None / 'reserve')
    - Назначение борта всем резервным экипажам без ВС (old_aircraft_id: None / 'reserve' -> new_aircraft_id: int)
    - Замена всех экипажей на МПД на новый борт (old_aircraft_id: 'all' -> new_aircraft_id: int)
    """
    from django.db import transaction
    from .models import FlightCrew, CrewMember, PilotAssignment
    from hrdepartment_app.models import PlaceProductionActivity
    from contracts_app.models import Estate

    try:
        mpd = PlaceProductionActivity.objects.get(id=mpd_id)
    except PlaceProductionActivity.DoesNotExist:
        return {'status': 'error', 'errors': ['МПД не найдено.']}

    if start_date > end_date:
        return {'status': 'error', 'errors': ['Начальная дата не может быть позже конечной.']}

    # Нормализация old_aircraft_id
    filter_mode = 'specific'
    old_aircraft = None
    if old_aircraft_id in [None, '', 'reserve', 'null']:
        filter_mode = 'reserve'
    elif old_aircraft_id == 'all':
        filter_mode = 'all'
    else:
        try:
            old_aircraft_id_int = int(old_aircraft_id)
            old_aircraft = Estate.objects.filter(id=old_aircraft_id_int).first()
            if not old_aircraft:
                return {'status': 'error', 'errors': ['Исходное воздушное судно не найдено.']}
        except (ValueError, TypeError):
            filter_mode = 'all'

    # Нормализация new_aircraft_id
    to_reserve = False
    new_aircraft = None
    if new_aircraft_id in [None, '', 'reserve', 'null', 0, '0']:
        to_reserve = True
    else:
        try:
            new_aircraft_id_int = int(new_aircraft_id)
            new_aircraft = Estate.objects.filter(id=new_aircraft_id_int).first()
            if not new_aircraft:
                return {'status': 'error', 'errors': ['Целевое воздушное судно не найдено.']}
        except (ValueError, TypeError):
            to_reserve = True

    # 1. Проверка конфликтов для new_aircraft (не занят ли на других МПД)
    if new_aircraft:
        conflicts = []
        existing_other_crews = FlightCrew.objects.filter(
            aircraft=new_aircraft,
            date__gte=start_date,
            date__lte=end_date
        ).exclude(mpd_id=mpd_id).select_related('mpd')

        for ex in existing_other_crews:
            conflicts.append(
                f"Борт {new_aircraft.registration_number} на дату {ex.date.strftime('%d.%m.%Y')} уже занят экипажем на {ex.mpd.name}."
            )

        if conflicts:
            return {
                'status': 'error',
                'errors': conflicts
            }

    # 2. Выборка целевых экипажей на МПД
    crews_qs = FlightCrew.objects.filter(
        mpd=mpd,
        date__gte=start_date,
        date__lte=end_date
    ).select_related('aircraft', 'mpd').prefetch_related('members')

    if filter_mode == 'specific' and old_aircraft:
        crews_qs = crews_qs.filter(aircraft=old_aircraft)
    elif filter_mode == 'reserve':
        crews_qs = crews_qs.filter(aircraft__isnull=True)

    target_crews = list(crews_qs)
    if not target_crews:
        return {
            'status': 'success',
            'updated_count': 0,
            'message': 'Экипажей, соответствующих условиям фильтра, не найдено.'
        }

    updated_count = 0
    with transaction.atomic():
        for crew in target_crews:
            if to_reserve:
                crew.aircraft = None
                if not crew.name or crew.name == 'standard':
                    crew.name = 'Резерв'
                crew.save()
                updated_count += 1
            else:
                # Проверяем, нет ли на этом же МПД на эту дату другого экипажа с new_aircraft
                duplicate_crew = FlightCrew.objects.filter(
                    mpd=mpd,
                    date=crew.date,
                    aircraft=new_aircraft
                ).exclude(id=crew.id).first()

                if duplicate_crew:
                    # Если уже есть экипаж с этим бортом, переносим участников
                    for m in crew.members.all():
                        CrewMember.objects.update_or_create(
                            crew=duplicate_crew,
                            member=m.member,
                            defaults={'role': m.role}
                        )
                        PilotAssignment.objects.filter(
                            pilot=m.member,
                            date=crew.date
                        ).update(crew=duplicate_crew, role_in_crew=m.role)
                    crew.delete()
                    updated_count += 1
                else:
                    crew.aircraft = new_aircraft
                    crew.save()
                    updated_count += 1

        clean_empty_flight_crews(mpd_id=mpd_id, start_date=start_date, end_date=end_date)

    new_ac_name = new_aircraft.registration_number if new_aircraft else "Резерв"
    old_ac_name = old_aircraft.registration_number if old_aircraft else (
        "Резерв" if filter_mode == 'reserve' else "Все")
    return {
        'status': 'success',
        'updated_count': updated_count,
        'message': f"Успешно заменен борт ({old_ac_name} → {new_ac_name}) в {updated_count} экипажах на МПД «{mpd.name}»."
    }


def delete_flight_crew(crew_id: int) -> bool:
    """Удаляет экипаж и отвязывает связанные назначения PilotAssignment.

    Args:
        crew_id (int): Идентификатор экипажа.

    Returns:
        bool: True при успешном удалении, иначе False.
    """
    from .models import FlightCrew, PilotAssignment
    try:
        crew = FlightCrew.objects.get(id=crew_id)
        PilotAssignment.objects.filter(crew=crew).update(crew=None, role_in_crew="")
        crew.delete()
        return True
    except FlightCrew.DoesNotExist:
        return False


def get_month_name_ru(month: int) -> str:
    """Возвращает русское наименование месяца в именительном падеже.

    Args:
        month (int): Номер месяца (1-12).

    Returns:
        str: Название месяца на русском языке.
    """
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    if 1 <= month <= 12:
        return months[month - 1]
    return f"Месяц {month}"


def build_flight_planning_snapshot(year: int, month: int) -> Dict[str, Any]:
    """Формирует полный неизменяемый снимок (JSON Snapshot) сетки планирования полетов за месяц.

    Собирает все места деятельности (МПД), активные ВС, даты месяца, сформированные экипажи,
    составы экипажей с ролями и ФИО пилотов, пометки к полетам, а также нераспределенные назначения.

    Args:
        year (int): Год планирования.
        month (int): Номер месяца (1-12).

    Returns:
        Dict[str, Any]: Сериализуемый словарь со всей структурой сетки планирования.
    """
    from .models import FlightCrew, PilotAssignment, CREW_ROLES, FLIGHT_TYPES
    from hrdepartment_app.models import PlaceProductionActivity

    # Определяем диапазон дат
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    dates_list = []
    curr = start_date
    while curr <= end_date:
        dates_list.append(curr.isoformat())
        curr += timedelta(days=1)

    mpds = PlaceProductionActivity.objects.filter(in_planning=True).order_by('name')
    mpds_data = [
        {
            'id': m.id,
            'name': m.name,
            'short_name': m.short_name or m.name
        }
        for m in mpds
    ]

    roles_dict = dict(CREW_ROLES)
    flight_types_dict = dict(FLIGHT_TYPES)

    # Загружаем все экипажи за месяц
    crews_qs = FlightCrew.objects.filter(
        date__year=year,
        date__month=month
    ).select_related('mpd', 'aircraft', 'aircraft__type_property').prefetch_related(
        'members',
        'members__member',
        'members__member__user_work_profile__job',
        'notes',
        'notes__author'
    )

    grid: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    total_crews_count = 0
    pilots_set = set()
    aircrafts_set = set()

    for crew in crews_qs:
        mpd_key = str(crew.mpd_id)
        date_key = crew.date.isoformat()

        if mpd_key not in grid:
            grid[mpd_key] = {}
        if date_key not in grid[mpd_key]:
            grid[mpd_key][date_key] = []

        total_crews_count += 1
        if crew.aircraft_id:
            aircrafts_set.add(crew.aircraft_id)

        # Собираем участников
        members_data = []
        for m in crew.members.all():
            p = m.member
            pilots_set.add(p.id)
            job_name = ""
            if hasattr(p, 'user_work_profile') and p.user_work_profile and p.user_work_profile.job:
                job_name = p.user_work_profile.job.name

            pilot_display_name = p.title or f"{p.last_name} {p.first_name}".strip() or p.username
            members_data.append({
                'pilot_id': p.id,
                'member_id': p.id,
                'id': p.id,
                'name': pilot_display_name,
                'pilot_name': pilot_display_name,
                'role': m.role,
                'role_label': roles_dict.get(m.role, m.role),
                'job': job_name
            })

        # Сортируем участников по иерархии ролей (КВС -> Второй пилот -> Инструктор -> Бортмеханик)
        role_priority = {
            'commander': 1,
            'copilot': 2,
            'pilot_instructor': 3,
            'flight_engineer': 4,
            'flight_engineer_instructor': 5
        }
        members_data.sort(key=lambda x: role_priority.get(x['role'], 99))

        # Собираем пометки
        notes_data = []
        for n in crew.notes.all():
            author_title = n.author.title if (n.author and n.author.title) else (
                n.author.username if n.author else "Аноним")
            notes_data.append({
                'id': n.id,
                'author_name': author_title,
                'author_role': n.author_role,
                'message': n.message,
                'created_at': n.created_at.strftime('%d.%m.%Y %H:%M'),
                'created_at_time': n.created_at.strftime('%H:%M')
            })

        crew_obj = {
            'crew_id': crew.id,
            'id': crew.id,
            'flight_type': crew.flight_type,
            'flight_type_label': flight_types_dict.get(crew.flight_type, crew.flight_type),
            'name': crew.name,
            'comment': crew.comment,
            'aircraft_id': crew.aircraft_id,
            'aircraft_number': crew.aircraft.registration_number if crew.aircraft else 'Резерв',
            'aircraft_reg': crew.aircraft.registration_number if crew.aircraft else 'Резерв',
            'aircraft_type': crew.aircraft.type_property.type_property if (
                    crew.aircraft and crew.aircraft.type_property) else '',
            'members': members_data,
            'notes': notes_data
        }
        grid[mpd_key][date_key].append(crew_obj)

    snapshot = {
        'version_format': 1,
        'year': year,
        'month': month,
        'month_name': get_month_name_ru(month),
        'dates': dates_list,
        'mpds': mpds_data,
        'grid': grid,
        'summary': {
            'total_crews': total_crews_count,
            'pilots_count': len(pilots_set),
            'aircrafts_count': len(aircrafts_set)
        }
    }
    return snapshot


def calculate_flight_planning_diff(
        old_snapshot: Dict[str, Any],
        new_snapshot: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Вычисляет детальную разницу (diff) между двумя снимками сетки планирования.

    Сравнивает экипажи по МПД и датам, выявляя добавление/удаление экипажей,
    замену воздушного судна, изменение типа полета и замену/добавление/удаление членов экипажа.

    Args:
        old_snapshot (Dict[str, Any]): Предыдущий снимок (эталон).
        new_snapshot (Dict[str, Any]): Новый снимок (текущее состояние).

    Returns:
        List[Dict[str, Any]]: Список зафиксированных изменений с описанием и метаданными.
    """
    diff_list: List[Dict[str, Any]] = []

    old_grid = old_snapshot.get('grid', {})
    new_grid = new_snapshot.get('grid', {})

    mpds_dict = {str(m['id']): m['name'] for m in new_snapshot.get('mpds', [])}
    for m in old_snapshot.get('mpds', []):
        mpds_dict[str(m['id'])] = m['name']

    all_dates = sorted(list(set(old_snapshot.get('dates', []) + new_snapshot.get('dates', []))))
    all_mpd_keys = sorted(list(set(list(old_grid.keys()) + list(new_grid.keys()))))

    for mpd_key in all_mpd_keys:
        mpd_name = mpds_dict.get(mpd_key, f"МПД #{mpd_key}")
        old_mpd_dates = old_grid.get(mpd_key, {})
        new_mpd_dates = new_grid.get(mpd_key, {})

        for date_str in all_dates:
            old_crews = old_mpd_dates.get(date_str, [])
            new_crews = new_mpd_dates.get(date_str, [])

            # Преобразуем дату в формат ДД.ММ.ГГГГ для отображения
            try:
                d_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                date_formatted = d_obj.strftime('%d.%m.%Y')
            except Exception:
                date_formatted = date_str

            # 1. Если на эту дату и МПД ранее не было экипажей, а теперь появились
            if not old_crews and new_crews:
                for nc in new_crews:
                    ac = nc.get('aircraft_reg', 'Резерв')
                    members_str = ", ".join([f"{m['role_label']}: {m['pilot_name']}" for m in nc.get('members', [])])
                    diff_list.append({
                        'date': date_str,
                        'date_formatted': date_formatted,
                        'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                        'mpd_name': mpd_name,
                        'aircraft': ac,
                        'change_type': 'crew_added',
                        'description': f"Назначен новый экипаж ({ac}). Состав: {members_str or 'без назначений'}"
                    })
                continue

            # 2. Если экипажи были, а теперь удалены
            if old_crews and not new_crews:
                for oc in old_crews:
                    ac = oc.get('aircraft_reg', 'Резерв')
                    diff_list.append({
                        'date': date_str,
                        'date_formatted': date_formatted,
                        'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                        'mpd_name': mpd_name,
                        'aircraft': ac,
                        'change_type': 'crew_removed',
                        'description': f"Расформирован экипаж ({ac})"
                    })
                continue

            # 3. Сопоставляем экипажи (по борту или по индексу)
            max_len = max(len(old_crews), len(new_crews))
            for i in range(max_len):
                if i >= len(old_crews):
                    nc = new_crews[i]
                    ac = nc.get('aircraft_reg', 'Резерв')
                    members_str = ", ".join([f"{m['role_label']}: {m['pilot_name']}" for m in nc.get('members', [])])
                    diff_list.append({
                        'date': date_str,
                        'date_formatted': date_formatted,
                        'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                        'mpd_name': mpd_name,
                        'aircraft': ac,
                        'change_type': 'crew_added',
                        'description': f"Добавлен дополнительный экипаж ({ac}): {members_str}"
                    })
                    continue

                if i >= len(new_crews):
                    oc = old_crews[i]
                    ac = oc.get('aircraft_reg', 'Резерв')
                    diff_list.append({
                        'date': date_str,
                        'date_formatted': date_formatted,
                        'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                        'mpd_name': mpd_name,
                        'aircraft': ac,
                        'change_type': 'crew_removed',
                        'description': f"Снят дополнительный экипаж ({ac})"
                    })
                    continue

                oc = old_crews[i]
                nc = new_crews[i]

                old_ac = oc.get('aircraft_reg', 'Резерв')
                new_ac = nc.get('aircraft_reg', 'Резерв')
                if old_ac != new_ac:
                    diff_list.append({
                        'date': date_str,
                        'date_formatted': date_formatted,
                        'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                        'mpd_name': mpd_name,
                        'aircraft': f"{old_ac} → {new_ac}",
                        'change_type': 'aircraft_changed',
                        'description': f"Замена борта ВС: {old_ac} → {new_ac}"
                    })

                # Сравниваем участников по ролям
                old_members_map = {m['role']: m['pilot_name'] for m in oc.get('members', [])}
                new_members_map = {m['role']: m['pilot_name'] for m in nc.get('members', [])}
                all_roles = set(list(old_members_map.keys()) + list(new_members_map.keys()))

                for r in all_roles:
                    old_p = old_members_map.get(r)
                    new_p = new_members_map.get(r)
                    role_label = r
                    # Ищем читаемое имя роли
                    for m in nc.get('members', []) + oc.get('members', []):
                        if m['role'] == r and m.get('role_label'):
                            role_label = m['role_label']
                            break

                    if old_p and new_p and old_p != new_p:
                        diff_list.append({
                            'date': date_str,
                            'date_formatted': date_formatted,
                            'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                            'mpd_name': mpd_name,
                            'aircraft': new_ac,
                            'change_type': 'member_replaced',
                            'description': f"Замена {role_label}: {old_p} → {new_p}"
                        })
                    elif not old_p and new_p:
                        diff_list.append({
                            'date': date_str,
                            'date_formatted': date_formatted,
                            'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                            'mpd_name': mpd_name,
                            'aircraft': new_ac,
                            'change_type': 'member_added',
                            'description': f"Назначен {role_label}: {new_p}"
                        })
                    elif old_p and not new_p:
                        diff_list.append({
                            'date': date_str,
                            'date_formatted': date_formatted,
                            'mpd_id': int(mpd_key) if mpd_key.isdigit() else mpd_key,
                            'mpd_name': mpd_name,
                            'aircraft': new_ac,
                            'change_type': 'member_removed',
                            'description': f"Снят с рейса {role_label}: {old_p}"
                        })

    return diff_list


def get_next_document_number(year: int, month: int) -> Tuple[str, int]:
    """Генерирует следующий порядковый номер документа расстановки в формате ММ-ВВ/ГГГГ.

    Args:
        year (int): Год планирования.
        month (int): Месяц планирования.

    Returns:
        Tuple[str, int]: Кортеж (строка_номера, номер_версии).
    """
    from .models import FlightPlanningDocument
    existing_count = FlightPlanningDocument.objects.filter(year=year, month=month).count()
    version = existing_count + 1
    doc_number = f"{month:02d}-{version:02d}/{year}"
    return doc_number, version


def create_planning_document(
        year: int,
        month: int,
        author,
        reason: str = ""
):
    """Создает новый документ расстановки экипажей на месяц в статусе 'На утверждении'.

    Формирует снимок сетки планирования, сравнивает с предыдущей утвержденной версией,
    вычисляет реестр изменений (diff) и сохраняет объект FlightPlanningDocument.

    Args:
        year (int): Год планирования.
        month (int): Месяц планирования.
        author (DataBaseUser): Диспетчер, сформировавший документ.
        reason (str): Обоснование создания документа / внесения изменений.

    Returns:
        FlightPlanningDocument: Созданный экземпляр документа.
    """
    from .models import FlightPlanningDocument

    snapshot_data = build_flight_planning_snapshot(year, month)
    previous_doc = get_latest_approved_document(year, month)

    if previous_doc:
        diff_data = calculate_flight_planning_diff(previous_doc.snapshot_data, snapshot_data)
    else:
        diff_data = []

    doc_number, version = get_next_document_number(year, month)
    month_name = get_month_name_ru(month)
    title = f"План расстановки экипажей на {month_name} {year} г. (Редакция {version})"

    if not reason:
        if version == 1:
            reason = f"Плановая расстановка экипажей ВС на {month_name} {year} г."
        else:
            reason = f"Оперативная корректировка плана экипажей № {version}"

    document = FlightPlanningDocument.objects.create(
        number=doc_number,
        year=year,
        month=month,
        version=version,
        status='pending',
        title=title,
        reason=reason,
        author=author,
        snapshot_data=snapshot_data,
        diff_data=diff_data,
        previous_document=previous_doc
    )
    return document


def approve_planning_document(document, approver):
    """Утверждает документ расстановки экипажей, делая его действующим планом.

    Переводит все предыдущие утвержденные документы за этот месяц в статус 'archived',
    а текущий документ — в статус 'approved'.

    Args:
        document (FlightPlanningDocument): Документ для утверждения.
        approver (DataBaseUser): Руководитель, утверждающий документ.

    Returns:
        FlightPlanningDocument: Утвержденный документ.
    """
    from .models import FlightPlanningDocument
    from django.db import transaction
    from django.utils import timezone

    with transaction.atomic():
        FlightPlanningDocument.objects.filter(
            year=document.year,
            month=document.month,
            status='approved'
        ).exclude(id=document.id).update(status='archived')

        document.status = 'approved'
        document.approved_by = approver
        document.approved_at = timezone.now()
        document.save()

    return document


def get_latest_approved_document(year: int, month: int):
    """Возвращает последний утвержденный (действующий) документ расстановки экипажей на месяц.

    Args:
        year (int): Год планирования.
        month (int): Месяц планирования.

    Returns:
        Optional[FlightPlanningDocument]: Утвержденный документ или None.
    """
    from .models import FlightPlanningDocument
    return FlightPlanningDocument.objects.filter(
        year=year,
        month=month,
        status='approved'
    ).order_by('-version', '-created_at').first()


def get_pending_document(year: int, month: int):
    """Возвращает документ расстановки на месяц, ожидающий утверждения руководством.

    Args:
        year (int): Год планирования.
        month (int): Месяц планирования.

    Returns:
        Optional[FlightPlanningDocument]: Документ на утверждении или None.
    """
    from .models import FlightPlanningDocument
    return FlightPlanningDocument.objects.filter(
        year=year,
        month=month,
        status='pending'
    ).order_by('-version', '-created_at').first()


def check_snapshot_matches_live(
        year: int,
        month: int,
        document
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Сравнивает зафиксированный в документе снимок с текущим живым состоянием базы данных.

    Args:
        year (int): Год планирования.
        month (int): Месяц планирования.
        document (Optional[FlightPlanningDocument]): Сравниваемый документ.

    Returns:
        Tuple[bool, List[Dict[str, Any]]]: Кортеж (полное_совпадение, список_расхождений).
    """
    if not document or not document.snapshot_data:
        return False, []

    live_snapshot = build_flight_planning_snapshot(year, month)
    diff = calculate_flight_planning_diff(document.snapshot_data, live_snapshot)
    return len(diff) == 0, diff


def calculate_check_end_date(
        start_date: date,
        validity_months: int,
        validity_days: int = 0
) -> date:
    """Вычисляет дату окончания действия периодической проверки.

    К дате начала прибавляются указанные месяцы и дополнительные дни.
    Корректно обрабатывает високосные годы и разную длину месяцев.

    Args:
        start_date (date): Дата начала прохождения проверки.
        validity_months (int): Периодичность действия в месяцах.
        validity_days (int, optional): Дополнительные дни. По умолчанию 0.

    Returns:
        date: Расчетная дата окончания действия проверки.
    """
    month_total = (start_date.month - 1) + validity_months
    new_year = start_date.year + (month_total // 12)
    new_month = (month_total % 12) + 1

    if new_month == 12:
        last_day_of_month = (date(new_year + 1, 1, 1) - timedelta(days=1)).day
    else:
        last_day_of_month = (date(new_year, new_month + 1, 1) - timedelta(days=1)).day

    new_day = min(start_date.day, last_day_of_month)
    res_date = date(new_year, new_month, new_day)

    if validity_days:
        res_date += timedelta(days=validity_days)

    return res_date


def get_employee_check_assignments(employee_id: int) -> Dict[str, Any]:
    """Возвращает информацию о закрепленных за сотрудником обязательных периодических проверках.

    Args:
        employee_id (int): Идентификатор сотрудника (DataBaseUser.id).

    Returns:
        Dict[str, Any]: Словарь с ключами:
            - 'employee_id' (int): ID сотрудника;
            - 'employee_name' (str): ФИО сотрудника;
            - 'assigned_check_type_ids' (List[int]): Список ID закрепленных проверок;
            - 'all_check_types' (List[Dict[str, Any]]): Список всех активных проверок с метаданными.
    """
    from customers_app.models import DataBaseUser
    from .models import PeriodicCheckType, EmployeeRequiredCheck

    employee = DataBaseUser.objects.select_related('user_work_profile__job').filter(id=employee_id).first()
    if not employee:
        return {'status': 'error', 'error': 'Сотрудник не найден.'}

    # Все активные типы проверок
    all_types = PeriodicCheckType.objects.filter(is_active=True).select_related('aircraft_type').order_by('order',
                                                                                                          'name')

    # Текущие закрепления
    assigned_records = EmployeeRequiredCheck.objects.filter(employee_id=employee_id)
    has_custom_assignments = assigned_records.exists()

    if has_custom_assignments:
        assigned_ids = set(assigned_records.filter(is_required=True).values_list('check_type_id', flat=True))
    else:
        # По умолчанию определяем подходящие проверки по должности
        job_name = ""
        if hasattr(employee, 'user_work_profile') and employee.user_work_profile and employee.user_work_profile.job:
            job_name = employee.user_work_profile.job.name.lower()

        is_pilot = ('пилот' in job_name or 'командир' in job_name or 'квс' in job_name)
        is_fe = ('механик' in job_name or 'инженер' in job_name or 'бм' in job_name)
        is_tech = ('техник' in job_name)

        assigned_ids = set()
        for ct in all_types:
            if ct.applies_to == 'pilots' and not is_pilot and (is_fe or is_tech):
                continue
            if ct.applies_to == 'flight_engineers' and not is_fe and (is_pilot or is_tech):
                continue
            if ct.applies_to == 'technicians' and not is_tech and (is_pilot or is_fe):
                continue
            if ct.applies_to == 'crew' and not is_pilot and not is_fe and is_tech:
                continue
            assigned_ids.add(ct.id)

    types_data = []
    for ct in all_types:
        types_data.append({
            'id': ct.id,
            'name': ct.name,
            'code': ct.code or "",
            'aircraft_display': ct.aircraft_display,
            'validity_months': ct.validity_months,
            'validity_days': ct.validity_days,
            'applies_to': ct.applies_to,
            'applies_to_display': ct.get_applies_to_display(),
            'is_assigned': ct.id in assigned_ids
        })

    return {
        'status': 'success',
        'employee_id': employee.id,
        'employee_name': employee.title or f"{employee.last_name} {employee.first_name}".strip() or employee.username,
        'employee_job': employee.user_work_profile.job.name if hasattr(employee,
                                                                       'user_work_profile') and employee.user_work_profile and employee.user_work_profile.job else "",
        'has_custom_assignments': has_custom_assignments,
        'assigned_check_type_ids': list(assigned_ids),
        'all_check_types': types_data
    }


def save_employee_check_assignments(
        employee_id: int,
        check_type_ids: List[int],
        assigned_by: Optional[Any] = None
) -> None:
    """Сохраняет индивидуальный перечень обязательных периодических проверок для сотрудника.

    Args:
        employee_id (int): Идентификатор сотрудника (DataBaseUser.id).
        check_type_ids (List[int]): Список идентификаторов проверок, обязательных к сдаче.
        assigned_by (Optional[DataBaseUser]): Пользователь, назначивший проверки.
    """
    from .models import PeriodicCheckType, EmployeeRequiredCheck

    active_type_ids = set(PeriodicCheckType.objects.filter(is_active=True).values_list('id', flat=True))
    target_ids_set = set(int(cid) for cid in check_type_ids if int(cid) in active_type_ids)

    # Обновляем или создаем записи закрепления для всех активных типов проверок
    all_active_types = PeriodicCheckType.objects.filter(is_active=True)
    for ct in all_active_types:
        should_be_required = ct.id in target_ids_set
        EmployeeRequiredCheck.objects.update_or_create(
            employee_id=employee_id,
            check_type_id=ct.id,
            defaults={
                'is_required': should_be_required,
                'assigned_by': assigned_by
            }
        )


def get_batch_employee_check_assignments(employee_ids: List[int]) -> Dict[int, Set[int]]:
    """Пакетная выгрузка закрепленных проверок для списка сотрудников без N+1 запросов.

    Args:
        employee_ids (List[int]): Список идентификаторов сотрудников.

    Returns:
        Dict[int, Set[int]]: Словарь, сопоставляющий employee_id с множеством ID обязательных проверок.
            Если для сотрудника нет индивидуальных записей, возвращается None в качестве индикатора
            использования дефолтных правил должности.
    """
    from .models import EmployeeRequiredCheck

    assignments_qs = EmployeeRequiredCheck.objects.filter(
        employee_id__in=employee_ids
    ).values('employee_id', 'check_type_id', 'is_required')

    res: Dict[int, Optional[Set[int]]] = {}
    for row in assignments_qs:
        emp_id = row['employee_id']
        if emp_id not in res:
            res[emp_id] = set()
        if row['is_required']:
            res[emp_id].add(row['check_type_id'])

    return res


def get_pilot_periodic_check_status(
        pilot_id: int,
        target_date: Optional[date] = None,
        aircraft_type_id: Optional[int] = None
) -> Dict[str, Any]:
    """Вычисляет полный статус периодических проверок сотрудника на указанную дату.

    Проверяет актуальность только тех проверок, которые индивидуально закреплены
    за данным сотрудником (или подходят ему по должности).
    Уволенные и неактивные сотрудники исключаются из контроля.

    Args:
        pilot_id (int): Идентификатор сотрудника (DataBaseUser).
        target_date (Optional[date]): Проверяемая дата полета. По умолчанию сегодня.
        aircraft_type_id (Optional[int]): Идентификатор типа ВС (TypeProperty.id).

    Returns:
        Dict[str, Any]: Словарь со статусом, списком проверок и агрегированными флагами.
    """
    from customers_app.models import DataBaseUser
    from .models import PeriodicCheckType, PeriodicCheckRecord, EmployeeRequiredCheck

    if target_date is None:
        target_date = date.today()

    pilot = DataBaseUser.objects.filter(id=pilot_id).select_related('user_work_profile__job').first()
    if not pilot:
        return {
            'pilot_id': pilot_id,
            'pilot_name': 'Неизвестный сотрудник',
            'has_issues': False,
            'has_expired': False,
            'has_warning': False,
            'badge_status': 'ok',
            'badge_icon': 'bx-check-circle text-success',
            'warnings_count': 0,
            'expired_count': 0,
            'missing_count': 0,
            'valid_count': 0,
            'total_checks': 0,
            'details': [],
            'checks': [],
            'summary_text': 'Сотрудник не найден'
        }

    pilot_name = pilot.title or f"{pilot.last_name} {pilot.first_name}".strip()

    # Если сотрудник уволен или не активен — контроль проверок полностью отключается
    if not pilot.is_active:
        return {
            'pilot_id': pilot_id,
            'pilot_name': pilot_name,
            'is_dismissed': True,
            'has_issues': False,
            'has_expired': False,
            'has_warning': False,
            'badge_status': 'ok',
            'badge_icon': 'bx-user-x text-muted',
            'warnings_count': 0,
            'expired_count': 0,
            'missing_count': 0,
            'valid_count': 0,
            'total_checks': 0,
            'details': [],
            'checks': [],
            'summary_text': 'Сотрудник не активен / уволен (контроль проверок отключен)'
        }

    job_name = ""
    if hasattr(pilot, 'user_work_profile') and pilot.user_work_profile and pilot.user_work_profile.job:
        job_name = pilot.user_work_profile.job.name.lower()

    is_pilot = ('пилот' in job_name or 'командир' in job_name or 'квс' in job_name)
    is_fe = ('механик' in job_name or 'инженер' in job_name or 'бм' in job_name)
    is_tech = ('техник' in job_name)

    check_types_qs = PeriodicCheckType.objects.filter(is_active=True).select_related('aircraft_type').order_by('order',
                                                                                                               'name')

    # Проверяем наличие индивидуальных закреплений проверок за сотрудником
    custom_assignments_exist = EmployeeRequiredCheck.objects.filter(employee_id=pilot_id).exists()
    if custom_assignments_exist:
        required_check_ids = set(
            EmployeeRequiredCheck.objects.filter(
                employee_id=pilot_id,
                is_required=True
            ).values_list('check_type_id', flat=True)
        )
    else:
        required_check_ids = None

    applicable_check_types = []
    for ct in check_types_qs:
        if required_check_ids is not None:
            # Строго индивидуальное закрепление: проверка обязательна только если входит в required_check_ids
            if ct.id not in required_check_ids:
                continue
        else:
            # Дефолтная логика по категории должности
            if ct.applies_to == 'pilots' and not is_pilot and (is_fe or is_tech):
                continue
            if ct.applies_to == 'flight_engineers' and not is_fe and (is_pilot or is_tech):
                continue
            if ct.applies_to == 'technicians' and not is_tech and (is_pilot or is_fe):
                continue
            if ct.applies_to == 'crew' and not is_pilot and not is_fe and is_tech:
                continue

        if ct.aircraft_type_id:
            if aircraft_type_id:
                if ct.aircraft_type_id != aircraft_type_id:
                    continue
            else:
                has_passed_ever = PeriodicCheckRecord.objects.filter(employee_id=pilot_id, check_type=ct).exists()
                if not has_passed_ever:
                    continue

        applicable_check_types.append(ct)

    latest_records: Dict[int, PeriodicCheckRecord] = {}
    records_qs = PeriodicCheckRecord.objects.filter(
        employee_id=pilot_id,
        check_type__in=applicable_check_types
    ).select_related('check_type', 'aircraft_type').order_by('-end_date', '-start_date')

    for rec in records_qs:
        if rec.check_type_id not in latest_records:
            latest_records[rec.check_type_id] = rec

    details = []
    expired_count = 0
    warning_count = 0
    missing_count = 0
    valid_count = 0

    for ct in applicable_check_types:
        rec = latest_records.get(ct.id)
        ac_name = ct.aircraft_display

        if not rec:
            missing_count += 1
            details.append({
                'check_type_id': ct.id,
                'check_name': ct.name,
                'check_type_name': ct.name,
                'aircraft_type_id': ct.aircraft_type_id,
                'aircraft_type_name': ac_name,
                'status': 'missing',
                'status_label': 'Не пройдена',
                'badge_class': 'badge bg-danger',
                'start_date': None,
                'end_date': None,
                'days_remaining': None,
                'days_left': None,
                'document_number': '',
                'issued_by': '',
                'message': f"Мероприятие «{ct.name}» [{ac_name}] не имеет записей о прохождении"
            })
        else:
            st = rec.status_on_date(target_date)
            days_left = (rec.end_date - target_date).days

            if st == 'expired':
                expired_count += 1
                badge_class = 'badge bg-danger'
                status_label = 'Просрочено'
                msg = f"Мероприятие «{ct.name}» [{ac_name}] просрочено с {rec.end_date.strftime('%d.%m.%Y')}"
            elif st == 'warning':
                warning_count += 1
                badge_class = 'badge bg-warning text-dark'
                status_label = f"Истекает ({days_left} дн.)"
                msg = f"Мероприятие «{ct.name}» [{ac_name}] истекает через {days_left} дн. (до {rec.end_date.strftime('%d.%m.%Y')})"
            else:
                valid_count += 1
                badge_class = 'badge bg-success'
                status_label = 'Действует'
                msg = f"Мероприятие «{ct.name}» [{ac_name}] действует до {rec.end_date.strftime('%d.%m.%Y')}"

            details.append({
                'check_type_id': ct.id,
                'check_name': ct.name,
                'check_type_name': ct.name,
                'record_id': rec.id,
                'aircraft_type_id': rec.aircraft_type_id or ct.aircraft_type_id,
                'aircraft_type_name': ac_name,
                'status': st,
                'status_label': status_label,
                'badge_class': badge_class,
                'start_date': rec.start_date.strftime('%d.%m.%Y'),
                'end_date': rec.end_date.strftime('%d.%m.%Y'),
                'days_remaining': days_left,
                'days_left': days_left,
                'document_number': rec.document_number,
                'issued_by': rec.issued_by,
                'message': msg
            })

    has_expired = (expired_count + missing_count) > 0
    has_warning = warning_count > 0
    has_issues = has_expired or has_warning

    if has_expired:
        badge_status = 'danger'
        badge_icon = 'bx-error-circle text-danger'
        summary_text = f"Просрочено/отсутствует мероприятий: {expired_count + missing_count}"
    elif has_warning:
        badge_status = 'warning'
        badge_icon = 'bx-time-five text-warning'
        summary_text = f"Истекает в течение 30 дней мероприятий: {warning_count}"
    else:
        badge_status = 'ok'
        badge_icon = 'bx-check-circle text-success'
        summary_text = "Все обязательные периодические мероприятия пройдены и действуют"

    return {
        'pilot_id': pilot_id,
        'pilot_name': pilot_name,
        'target_date': target_date.strftime('%d.%m.%Y'),
        'has_issues': has_issues,
        'has_expired': has_expired,
        'has_warning': has_warning,
        'badge_status': badge_status,
        'badge_icon': badge_icon,
        'warnings_count': warning_count,
        'expired_count': expired_count,
        'missing_count': missing_count,
        'valid_count': valid_count,
        'total_checks': len(applicable_check_types),
        'details': details,
        'checks': details,
        'summary_text': summary_text
    }


def get_month_pilots_check_status_map(
        pilot_ids: List[int],
        year: int,
        month: int
) -> Dict[int, Dict[str, Any]]:
    """Оптимизированный пакетный расчет статуса проверок для списка пилотов на конкретный месяц.

    Args:
        pilot_ids (List[int]): Список идентификаторов сотрудников.
        year (int): Год планирования.
        month (int): Месяц планирования.

    Returns:
        Dict[int, Dict[str, Any]]: Карта { pilot_id: status_dict }.
    """
    today = date.today()
    if today.year == year and today.month == month:
        target_date = today
    else:
        target_date = date(year, month, 15)

    status_map = {}
    for pid in set(pilot_ids):
        status_map[pid] = get_pilot_periodic_check_status(pid, target_date)
    return status_map


def get_month_employee_statuses_map(
        pilot_ids: List[int],
        year: int,
        month: int
) -> Dict[int, List[Dict[str, Any]]]:
    """Формирует карту активных состояний/статусов сотрудников на выбранный месяц.

    Используется для быстрого отображения бейджей/предупреждений в шахматке планирования
    и в сборщике экипажей (Отпуск, Больничный, Резерв, КПК, ВЛЭК и др.).

    Args:
        pilot_ids (List[int]): Список идентификаторов сотрудников.
        year (int): Год планирования.
        month (int): Месяц (1-12).

    Returns:
        Dict[int, List[Dict[str, Any]]]: Словарь вида { pilot_id: [status_records_data] }.
    """
    from .models import EmployeeStatusRecord
    from hrdepartment_app.models import ReportCard
    from collections import defaultdict

    start_of_month = date(year, month, 1)
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

    records = EmployeeStatusRecord.objects.filter(
        employee_id__in=pilot_ids,
        start_date__lte=end_of_month,
        end_date__gte=start_of_month
    ).select_related('employee', 'status_type').order_by('start_date')

    status_map = defaultdict(list)
    for r in records:
        status_map[r.employee_id].append({
            'id': r.id,
            'source': 'lpc',
            'status_name': r.status_type.name,
            'status_code': r.status_type.code,
            'color': r.status_type.color,
            'is_blocking': r.status_type.is_blocking,
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'start_date_formatted': r.start_date.strftime('%d.%m.%Y'),
            'end_date_formatted': r.end_date.strftime('%d.%m.%Y'),
            'period_display': f"{r.start_date.strftime('%d.%m')}–{r.end_date.strftime('%d.%m')}",
            'document_number': r.document_number,
            'notes': r.notes
        })

    # Добавляем подтвержденные записи из табеля 1С (ReportCard)
    rc_types = list(REPORT_CARD_STATUS_CONFIG.keys())
    rc_month = ReportCard.objects.filter(
        employee_id__in=pilot_ids,
        report_card_day__gte=start_of_month,
        report_card_day__lte=end_of_month,
        record_type__in=rc_types
    ).prefetch_related('place_report_card')

    for rc in rc_month:
        meta = REPORT_CARD_STATUS_CONFIG.get(rc.record_type)
        if not meta:
            continue
        emp_id = rc.employee_id
        day_iso = rc.report_card_day.isoformat()
        day_fmt = rc.report_card_day.strftime('%d.%m.%Y')

        mpd_info = ""
        if rc.record_type in ('14', '15'):
            places = [p.name for p in rc.place_report_card.all()]
            if places:
                mpd_info = f" ({', '.join(places)})"

        status_map[emp_id].append({
            'id': f"rc_{rc.id}",
            'source': 'report_card',
            'status_name': f"[Табель 1С] {meta['full_name']}{mpd_info}",
            'status_code': meta['code'],
            'color': meta['color'],
            'is_blocking': meta['is_blocking'],
            'start_date': day_iso,
            'end_date': day_iso,
            'start_date_formatted': day_fmt,
            'end_date_formatted': day_fmt,
            'period_display': rc.report_card_day.strftime('%d.%m'),
            'document_number': rc.reason_adjustment or '',
            'notes': f"Запись табеля 1С (код {rc.record_type}){mpd_info}"
        })

    return dict(status_map)


def get_pilot_employee_statuses(
        pilot_id: int,
        target_date: Optional[date] = None
) -> Dict[str, Any]:
    """Возвращает информацию о текущих и запланированных состояниях сотрудника.

    Args:
        pilot_id (int): Идентификатор сотрудника.
        target_date (Optional[date], optional): Целевая дата проверки. Defaults to today.

    Returns:
        Dict[str, Any]: Словарь с активным статусом на дату и списком всех записей.
    """
    from .models import EmployeeStatusRecord
    if target_date is None:
        target_date = date.today()

    records = EmployeeStatusRecord.objects.filter(
        employee_id=pilot_id
    ).select_related('status_type').order_by('-start_date')

    active_records = [r for r in records if r.is_active_on_date(target_date)]
    active_status = active_records[0] if active_records else None

    records_data = []
    for r in records:
        records_data.append({
            'id': r.id,
            'status_name': r.status_type.name,
            'status_code': r.status_type.code,
            'color': r.status_type.color,
            'is_blocking': r.status_type.is_blocking,
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'document_number': r.document_number,
            'notes': r.notes,
            'is_current': r.is_active_on_date(target_date)
        })

    return {
        'pilot_id': pilot_id,
        'target_date': target_date.isoformat(),
        'has_active_status': active_status is not None,
        'active_status_name': active_status.status_type.name if active_status else None,
        'active_status_color': active_status.status_type.color if active_status else None,
        'records': records_data
    }


def get_today_active_statuses_summary(
        pilots_list: Sequence[Any],
        today: Optional[date] = None
) -> Dict[str, int]:
    """Формирует сводные счетчики KPI по активным состояниям сотрудников на указанную дату.

    Агрегирует данные без дублирования сотрудников из двух источников:
    - Оперативные записи ЛПК (`EmployeeStatusRecord`)
    - Подтвержденные отметки табеля (`ReportCard` / 1С:ЗУП)

    Args:
        pilots_list (Sequence[Any]): Список или QuerySet сотрудников.
        today (Optional[date], optional): Дата среза. Defaults to date.today().

    Returns:
        Dict[str, int]: Словарь счетчиков KPI:
            - 'total_active_today_count': Общее число сотрудников со статусами сегодня.
            - 'sick_leave_today_count': Число сотрудников на больничном.
            - 'vacation_today_count': Число сотрудников в отпуске (включая график отпусков).
            - 'reserve_today_count': Число сотрудников в резерве.
            - 'training_today_count': Число сотрудников на КПК / ВЛЭК / медосмотре.
    """
    if today is None:
        today = date.today()

    pilot_ids = set(p.id for p in pilots_list)
    if not pilot_ids:
        return {
            'total_active_today_count': 0,
            'sick_leave_today_count': 0,
            'vacation_today_count': 0,
            'reserve_today_count': 0,
            'training_today_count': 0,
        }

    from .models import EmployeeStatusRecord
    from hrdepartment_app.models import ReportCard

    # 1. Записи ЛПК на сегодня
    today_lpc = EmployeeStatusRecord.objects.filter(
        employee_id__in=pilot_ids,
        start_date__lte=today,
        end_date__gte=today
    ).select_related('status_type')

    # 2. Записи ReportCard на сегодня
    rc_vacation_types = ['2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '18', '19']
    today_rc = ReportCard.objects.filter(
        employee_id__in=pilot_ids,
        report_card_day=today
    ).exclude(record_type='1').exclude(record_type='')

    # Множества сотрудников по категориям (дедупликация)
    sick_emps = set(today_lpc.filter(
        Q(status_type__code='SICK_LEAVE') | Q(status_type__name__icontains='Больничный')
    ).values_list('employee_id', flat=True))
    sick_emps.update(today_rc.filter(record_type='16').values_list('employee_id', flat=True))

    vacation_emps = set(today_lpc.filter(
        Q(status_type__code__in=['VACATION', 'EXTRA_VACATION']) | Q(status_type__name__icontains='Отпуск')
    ).values_list('employee_id', flat=True))
    vacation_emps.update(today_rc.filter(record_type__in=rc_vacation_types).values_list('employee_id', flat=True))

    reserve_emps = set(today_lpc.filter(
        Q(status_type__code='RESERVE') | Q(status_type__name__icontains='Резерв')
    ).values_list('employee_id', flat=True))

    training_emps = set(today_lpc.filter(
        Q(status_type__code__in=['KPK', 'VLEK', 'MEDICAL_EXAM']) |
        Q(status_type__name__icontains='КПК') |
        Q(status_type__name__icontains='ВЛЭК') |
        Q(status_type__name__icontains='Медосмотр')
    ).values_list('employee_id', flat=True))
    training_emps.update(today_rc.filter(record_type='17').values_list('employee_id', flat=True))

    total_active_emps = set(today_lpc.values_list('employee_id', flat=True))
    total_active_emps.update(today_rc.values_list('employee_id', flat=True))

    return {
        'total_active_today_count': len(total_active_emps),
        'sick_leave_today_count': len(sick_emps),
        'vacation_today_count': len(vacation_emps),
        'reserve_today_count': len(reserve_emps),
        'training_today_count': len(training_emps),
    }


def _build_status_card_html(
        source: str,
        name: str,
        abbr: str,
        color: str,
        date_display: str,
        period_info: Optional[str] = None,
        days_count: Optional[int] = None,
        mpd_name: Optional[str] = None,
        document_number: Optional[str] = None,
        notes: Optional[str] = None,
        is_blocking: bool = False,
        is_confirmed: bool = False,
) -> str:
    """Формирует презентабельную структурированную HTML-карточку для всплывающей подсказки ячейки статуса.

    Включает в себя:
    - Заголовок с цветным бейджем аббревиатуры и наименованием статуса;
    - Бейдж источника записи (1С:ЗУП Табель или ЛПК Оперативный);
    - Период действия с датами и количеством дней;
    - Выделенный блок МПД назначения для служебных поездок и командировок;
    - Реквизиты документов-оснований (приказ, больничный лист, распоряжение);
    - Служебные примечания / причину ручной корректировки;
    - Индикаторы блокировки экипажа и подтверждения.

    Args:
        source (str): Источник записи ('lpc' или 'report_card').
        name (str): Полное наименование статуса.
        abbr (str): 1-2 символьная аббревиатура.
        color (str): Цветовой HEX-код статуса.
        date_display (str): Дата дня в формате "ДД.ММ.ГГГГ".
        period_info (Optional[str], optional): Диапазон дат "с ДД.ММ по ДД.ММ.ГГГГ".
        days_count (Optional[int], optional): Длительность в календарных днях.
        mpd_name (Optional[str], optional): Наименование МПД (для командировок и служебных поездок).
        document_number (Optional[str], optional): Номер документа или приказа.
        notes (Optional[str], optional): Служебные примечания.
        is_blocking (bool, optional): Блокирует ли данный статус назначение в экипаж. Defaults to False.
        is_confirmed (bool, optional): Подтверждена ли запись (для СП). Defaults to False.

    Returns:
        str: HTML-разметка карточки для всплывающего тултипа.
    """
    from django.utils.html import escape

    safe_name = escape(name)
    safe_abbr = escape(abbr)

    if source == 'report_card':
        source_label = "1С:ЗУП Табель"
        source_bg = "#f1f5f9"
        source_color = "#475569"
        source_border = "#cbd5e1"
    else:
        source_label = "ЛПК Оперативный"
        source_bg = "#eff6ff"
        source_color = "#1d4ed8"
        source_border = "#bfdbfe"

    period_text = escape(period_info) if period_info else escape(date_display)
    days_badge = ""
    if days_count and days_count > 1:
        days_badge = f'<span style="background:#f1f5f9;color:#64748b;font-size:10px;font-weight:600;padding:1px 5px;border-radius:4px;margin-left:4px;">{days_count} дн.</span>'

    mpd_block = ""
    if mpd_name:
        safe_mpd = escape(str(mpd_name).strip())
        mpd_block = (
            f'<div style="display:flex;align-items:center;gap:6px;margin:5px 0;padding:5px 8px;'
            f'border-radius:6px;background-color:#f0fdf4;border:1px solid #bbf7d0;color:#166534;font-size:12px;">'
            f'<span style="font-size:14px;line-height:1;">📍</span>'
            f'<div style="min-width:0;line-height:1.25;">'
            f'<span style="font-weight:700;color:#15803d;margin-right:3px;">МПД:</span>'
            f'<span style="font-weight:600;color:#14532d;">{safe_mpd}</span>'
            f'</div></div>'
        )

    doc_block = ""
    if document_number:
        safe_doc = escape(str(document_number).strip())
        if safe_doc and safe_doc != '0':
            doc_block = (
                f'<div style="display:flex;align-items:center;gap:5px;color:#475569;font-size:11px;margin-bottom:3px;">'
                f'<span style="color:#64748b;">📄</span>'
                f'<span>Документ: <strong>{safe_doc}</strong></span>'
                f'</div>'
            )

    notes_block = ""
    if notes:
        safe_notes = escape(str(notes).strip())
        if safe_notes and safe_notes.lower() != name.lower():
            notes_block = (
                f'<div style="margin-top:4px;padding:4px 8px;border-radius:4px;background-color:#f8fafc;'
                f'border-left:3px solid #cbd5e1;color:#334155;font-size:11px;line-height:1.3;">'
                f'<span style="color:#64748b;font-weight:600;">Примечание:</span> {safe_notes}'
                f'</div>'
            )

    if is_blocking:
        blocking_html = '<span style="color:#dc2626;font-weight:600;display:inline-flex;align-items:center;gap:3px;"><span style="font-size:12px;">⛔</span> Блокирует экипаж</span>'
    else:
        blocking_html = '<span style="color:#16a34a;font-weight:500;display:inline-flex;align-items:center;gap:3px;"><span style="font-size:12px;">✓</span> Не блокирует полеты</span>'

    confirmed_html = ""
    if is_confirmed:
        confirmed_html = '<span style="color:#0284c7;font-weight:600;display:inline-flex;align-items:center;gap:3px;"><span style="font-size:12px;">✅</span> Подтверждено</span>'

    card_html = (
        f'<div class="status-card-item" style="padding:10px 12px;border-left:4px solid {color};background:#ffffff;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;">'
        f'<div style="display:flex;align-items:center;gap:6px;min-width:0;">'
        f'<span style="display:inline-block;background-color:{color};color:#ffffff;font-weight:700;font-size:11px;padding:2px 6px;border-radius:4px;line-height:1;">{safe_abbr}</span>'
        f'<span style="font-weight:700;font-size:13px;color:#0f172a;line-height:1.2;">{safe_name}</span>'
        f'</div>'
        f'<span style="font-size:10px;font-weight:600;padding:2px 6px;border-radius:10px;background:{source_bg};color:{source_color};border:1px solid {source_border};white-space:nowrap;">{source_label}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:5px;color:#475569;font-size:12px;margin-bottom:4px;">'
        f'<span style="color:#64748b;">📅</span>'
        f'<span style="font-weight:600;">{period_text}</span>'
        f'{days_badge}'
        f'</div>'
        f'{mpd_block}'
        f'{doc_block}'
        f'{notes_block}'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-top:6px;padding-top:5px;border-top:1px solid #f1f5f9;font-size:11px;">'
        f'{blocking_html}'
        f'{confirmed_html}'
        f'</div>'
        f'</div>'
    )
    return card_html


def get_combined_employee_occupancy_matrix(
        pilots_list: Sequence[Any],
        year: int,
        month: int,
        today: Optional[date] = None
) -> Tuple[List[Dict[str, Any]], List[date]]:
    """Формирует сводную матрицу занятости персонала на указанный месяц.

    Объединяет в единой календарной сетке:
    1. Оперативные записи модуля ЛПК (`EmployeeStatusRecord`):
       Отпуск, Больничный, Резерв, КПК, ВЛЭК, Медосмотр, Командировка, Отгул.
    2. Подтвержденные записи кадрового учета и табеля 1С (`ReportCard`):
       Все 19 регламентированных видов отсутствий (Ежегодный, Дополнительный,
       Без оплаты, Учебный, ЧАЭС, Декретный, Больничный, Медосмотр, График отпусков,
       Служебная поездка, Командировка, Санаторно-курортное лечение, Отгул).

    Для служебных поездок и командировок автоматически определяется и выводится
    наименование МПД назначения (из связей табеля с `PlaceProductionActivity`
    или согласованных служебных записок `OfficialMemo`).

    При наличии записей из обоих источников на один день, статусы агрегируются
    в список бейджей ячейки с устранением дубликатов одинаковых типов и
    приоритетной сортировкой (Больничный -> Отпуск -> ВЛЭК/МО -> Командировка -> План).

    Args:
        pilots_list (Sequence[Any]): Список или QuerySet отображаемых сотрудников.
        year (int): Год планирования (например, 2026).
        month (int): Месяц планирования (1-12).
        today (Optional[date], optional): Текущая дата для подсветки столбца "Сегодня".
            Defaults to date.today().

    Returns:
        Tuple[List[Dict[str, Any]], List[date]]: Кортеж, содержащий:
            - matrix_rows (List[Dict[str, Any]]): Список строк по каждому сотруднику:
                {
                    'pilot': DataBaseUser,
                    'pilot_name': str,
                    'job': str,
                    'cells': List[Dict[str, Any]],
                    'has_any_status': bool,
                    'status_count': int
                }
            - days_list (List[date]): Список дат всех дней выбранного месяца.
    """
    if today is None:
        today = date.today()

    start_of_month = date(year, month, 1)
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

    days_in_month = (end_of_month - start_of_month).days + 1
    days_list = [date(year, month, d) for d in range(1, days_in_month + 1)]

    pilot_ids = [p.id for p in pilots_list]
    if not pilot_ids:
        return [], days_list

    from .models import EmployeeStatusRecord
    from collections import defaultdict

    # Предзагрузка служебных записок (OfficialMemo) для быстрого разрешения МПД командировок / поездок
    from hrdepartment_app.models import OfficialMemo
    memo_mpd_map: Dict[Tuple[int, date], List[str]] = defaultdict(list)
    try:
        memos = OfficialMemo.objects.filter(
            person_id__in=pilot_ids,
            period_from__lte=end_of_month,
            period_for__gte=start_of_month
        ).prefetch_related('place_production_activity')

        for m in memos:
            p_names = [p.name for p in m.place_production_activity.all()]
            if not p_names:
                continue
            m_from = max(start_of_month, m.period_from) if m.period_from else start_of_month
            m_to = min(end_of_month, m.period_for) if m.period_for else end_of_month
            cur_d = m_from
            while cur_d <= m_to:
                memo_mpd_map[(m.person_id, cur_d)].extend(p_names)
                cur_d += timedelta(days=1)
    except Exception:
        pass

    # 1. Загрузка оперативных записей ЛПК (EmployeeStatusRecord)
    lpc_records = EmployeeStatusRecord.objects.filter(
        employee_id__in=pilot_ids,
        start_date__lte=end_of_month,
        end_date__gte=start_of_month
    ).select_related('employee', 'status_type').order_by('start_date')

    # Словарь (employee_id, date) -> list of badge dicts
    status_matrix_lookup: Dict[Tuple[int, date], List[Dict[str, Any]]] = defaultdict(list)

    for r in lpc_records:
        curr = max(start_of_month, r.start_date)
        last_d = min(end_of_month, r.end_date)
        code = r.status_type.code
        if code == 'VACATION':
            abbr = 'ОТ'
            prio = 20
        elif code == 'EXTRA_VACATION':
            abbr = 'ДО'
            prio = 21
        elif code == 'SICK_LEAVE':
            abbr = 'Б'
            prio = 10
        elif code == 'RESERVE':
            abbr = 'Р'
            prio = 50
        elif code == 'KPK':
            abbr = 'КПК'
            prio = 32
        elif code == 'VLEK':
            abbr = 'ВЛ'
            prio = 33
        elif code == 'MEDICAL_EXAM':
            abbr = 'МО'
            prio = 34
        elif code == 'BUSINESS_TRIP':
            abbr = 'КМ'
            prio = 40
        elif code == 'DAY_OFF':
            abbr = 'В'
            prio = 60
        else:
            abbr = (r.status_type.name[:2] if len(r.status_type.name) >= 2 else r.status_type.name).upper()
            prio = 45

        period_info = f"с {r.start_date.strftime('%d.%m')} по {r.end_date.strftime('%d.%m.%Y')}"
        days_cnt = r.duration_days

        while curr <= last_d:
            # Для командировок определяем МПД
            lpc_mpd = None
            if code == 'BUSINESS_TRIP':
                if (r.employee_id, curr) in memo_mpd_map:
                    lpc_mpd = ", ".join(dict.fromkeys(memo_mpd_map[(r.employee_id, curr)]))
                elif r.notes and ('мпд' in r.notes.lower() or 'база' in r.notes.lower()):
                    lpc_mpd = r.notes
                else:
                    lpc_mpd = "не указано"

            card_html = _build_status_card_html(
                source='lpc',
                name=r.status_type.name,
                abbr=abbr,
                color=r.status_type.color,
                date_display=curr.strftime('%d.%m.%Y'),
                period_info=period_info,
                days_count=days_cnt,
                mpd_name=lpc_mpd,
                document_number=r.document_number,
                notes=r.notes,
                is_blocking=r.status_type.is_blocking,
                is_confirmed=False,
            )

            badge = {
                'source': 'lpc',
                'abbr': abbr,
                'name': r.status_type.name,
                'color': r.status_type.color,
                'is_blocking': r.status_type.is_blocking,
                'tooltip': card_html,
                'priority': prio,
                'record_id': r.id,
                'mpd_name': lpc_mpd,
            }

            status_matrix_lookup[(r.employee_id, curr)].append(badge)
            curr += timedelta(days=1)

    # 2. Загрузка подтвержденных записей табеля ReportCard (1C:ЗУП)
    from hrdepartment_app.models import ReportCard
    rc_type_keys = list(REPORT_CARD_STATUS_CONFIG.keys())

    rc_records = ReportCard.objects.filter(
        employee_id__in=pilot_ids,
        report_card_day__gte=start_of_month,
        report_card_day__lte=end_of_month,
        record_type__in=rc_type_keys
    ).prefetch_related('place_report_card')

    for rc in rc_records:
        r_type = rc.record_type
        meta = REPORT_CARD_STATUS_CONFIG.get(r_type)
        if not meta:
            continue

        emp_id = rc.employee_id
        rc_day = rc.report_card_day
        rc_date_str = rc_day.strftime('%d.%m.%Y')

        # Определение МПД для служебных поездок и командировок
        mpd_name = None
        if r_type in ('14', '15'):
            direct_places = [p.name for p in rc.place_report_card.all()]
            if direct_places:
                mpd_name = ", ".join(dict.fromkeys(direct_places))
            elif (emp_id, rc_day) in memo_mpd_map:
                memo_places = memo_mpd_map[(emp_id, rc_day)]
                mpd_name = ", ".join(dict.fromkeys(memo_places))
            else:
                mpd_name = "не указано в табеле"

        reason = (rc.reason_adjustment or '').strip()
        notes_val = reason if (reason and reason.lower() != meta['name'].lower() and reason.lower() != meta['full_name'].lower()) else None

        rc_card_html = _build_status_card_html(
            source='report_card',
            name=meta['full_name'],
            abbr=meta['abbr'],
            color=meta['color'],
            date_display=rc_date_str,
            period_info=None,
            days_count=1,
            mpd_name=mpd_name,
            document_number=rc.doc_ref_key if (rc.doc_ref_key and rc.doc_ref_key != '0') else None,
            notes=notes_val,
            is_blocking=meta['is_blocking'],
            is_confirmed=rc.confirmed,
        )

        rc_badge = {
            'source': 'report_card',
            'abbr': meta['abbr'],
            'name': meta['full_name'],
            'color': meta['color'],
            'is_blocking': meta['is_blocking'],
            'tooltip': rc_card_html,
            'priority': meta.get('priority', 50),
            'record_id': rc.id,
            'record_type': r_type,
            'mpd_name': mpd_name,
        }

        existing_badges = status_matrix_lookup[(emp_id, rc_day)]
        # Проверяем на дубликат по типу записи или одинаковой аббревиатуре
        duplicate_badge = next((b for b in existing_badges if b.get('record_type') == r_type or b['abbr'] == meta['abbr']), None)
        if duplicate_badge:
            # Если у дубликата есть МПД, а у первого не было — дополняем тултип
            if mpd_name and not duplicate_badge.get('mpd_name'):
                duplicate_badge['tooltip'] = rc_card_html
                duplicate_badge['mpd_name'] = mpd_name
        else:
            existing_badges.append(rc_badge)

    # 3. Построение строк матрицы
    matrix_rows = []
    for p in pilots_list:
        p_name = p.title or f"{p.last_name} {p.first_name}".strip() or p.username
        job_name = (
            p.user_work_profile.job.name
            if (hasattr(p, 'user_work_profile') and p.user_work_profile and p.user_work_profile.job)
            else ''
        )
        p_cells = []
        has_any_status = False
        status_count = 0

        for d in days_list:
            badges = status_matrix_lookup.get((p.id, d), [])
            if badges:
                has_any_status = True
                status_count += 1
                # Сортируем бейджи по приоритету (наиболее важный статус сверху)
                sorted_badges = sorted(badges, key=lambda b: b.get('priority', 50))
                primary = sorted_badges[0]
                # Объединяем карточки статусов тонким изящным разделителем
                combined_tooltip = '<div style="height:1px;background:#e2e8f0;margin:0;"></div>'.join(
                    b['tooltip'] for b in sorted_badges
                )
                p_cells.append({
                    'date': d,
                    'is_today': (d == today),
                    'has_status': True,
                    'badges': sorted_badges,
                    'abbr': primary['abbr'],
                    'name': primary['name'],
                    'color': primary['color'],
                    'is_blocking': any(b.get('is_blocking', False) for b in sorted_badges),
                    'tooltip': combined_tooltip,
                    'record': None,
                })
            else:
                p_cells.append({
                    'date': d,
                    'is_today': (d == today),
                    'has_status': False,
                    'badges': [],
                    'abbr': '',
                    'name': '',
                    'color': '',
                    'is_blocking': False,
                    'tooltip': '',
                    'record': None,
                })

        matrix_rows.append({
            'pilot': p,
            'pilot_name': p_name,
            'job': job_name,
            'cells': p_cells,
            'has_any_status': has_any_status,
            'status_count': status_count,
        })

    return matrix_rows, days_list


# ==============================================================================
# СПРАВОЧНИК РАЗРЕШЕННЫХ ДОЛЖНОСТЕЙ АВИАЦИОННОГО ПЕРСОНАЛА И РАЗГРАНИЧЕНИЯ ДОСТУПА
# ==============================================================================

# 1. Летный состав (Летчики, Пилоты, Бортмеханики)
FLIGHT_CREW_JOB_NAMES = [
    "Командир воздушного судна Ми-8",
    "Второй пилот воздушного судна Ми-8",
    "Пилот-инструктор воздушного судна Ми-8",
    "Пилот-инспектор по БП",
    "Бортовой механик воздушного судна Ми-8",
    "Бортмеханик-инструктор воздушного судна Ми-8",
]

# 2. Инженерно-технический состав (Инженеры, Техники)
ENGINEERING_STAFF_JOB_NAMES = [
    "Техник авиационный по эксплуатации ВС",
    "Техник авиационный по эксплуатации систем ВС",
    "Инженер по эксплуатации ВС",
    "Ведущий инженер по эксплуатации ВС",
    "Инженер по эксплуатации систем ВС",
    "Ведущий инженер по эксплуатации систем ВС",
    "Инженер по качеству эксплуатации ВС",
    "Инженер по качеству эксплуатации систем ВС",
    "Старший инженер по качеству эксплуатации ВС",
    "Старший инженер по качеству эксплуатации систем ВС",
]

# 3. Полный перечень разрешенных должностей (Общий состав)
ALL_STAFF_JOB_NAMES = list(dict.fromkeys(FLIGHT_CREW_JOB_NAMES + ENGINEERING_STAFF_JOB_NAMES))


def get_user_personnel_scope(user) -> str:
    """Определяет категорию видимости персонала для пользователя на основе прав и принадлежности должности.

    Категории:
        - '0': Общий состав (видны все сотрудники: и летный, и инженерно-технический состав).
        - '1': Летный состав (видны только летчики / пилоты / бортмеханики).
        - '2': Инженерный состав (видны только инженеры и авиатехники).

    Args:
        user: Экземпляр пользователя DataBaseUser или None.

    Returns:
        str: Код категории ('0', '1' или '2').
    """
    if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'is_superuser', False):
        return '0'

    # 1. Проверка по ролевым группам ЛПК
    user_groups = set(user.groups.values_list('name', flat=True))
    if "[ЛПК] Инженерная служба (ИАС)" in user_groups and not (
        {"[ЛПК] Диспетчеры планирования", "Планирование полетов", "[ЛПК] Руководство", "Руководство"} & user_groups
    ):
        return '2'

    if "[ЛПК] Летная служба" in user_groups and not (
        {"[ЛПК] Диспетчеры планирования", "Планирование полетов", "[ЛПК] Руководство", "Руководство"} & user_groups
    ):
        return '1'

    if {"[ЛПК] Диспетчеры планирования", "Планирование полетов", "[ЛПК] Руководство", "Руководство", "[ЛПК] Кадры и охрана труда", "Отдел кадров"} & user_groups:
        return '0'

    # 2. Определение по профилю должности сотрудника
    profile = getattr(user, 'user_work_profile', None)
    if profile and profile.job:
        job = profile.job

        # Проверка через division_affiliation должности
        affil = getattr(job, 'division_affiliation', None)
        if affil:
            affil_name = (getattr(affil, 'name', '') or '').lower()
            if affil.pk == 2 or "летн" in affil_name:
                return '1'
            if affil.pk == 3 or "инженер" in affil_name:
                return '2'
            if affil.pk == 1 or "общ" in affil_name:
                return '0'

        # Если в Job явно указана принадлежность (type_of_job: "0", "1", "2")
        if job.type_of_job in ('1', '2', '0'):
            return job.type_of_job

        # Fallback сопоставление по точному наименованию должности
        j_name = (job.name or "").strip().lower()
        if any(j_name == name.lower() for name in FLIGHT_CREW_JOB_NAMES):
            return '1'
        if any(j_name == name.lower() for name in ENGINEERING_STAFF_JOB_NAMES):
            return '2'

    return '0'


def get_allowed_staff_queryset(
    user=None,
    target_scope: Optional[str] = None,
    extra_user_id: Optional[int] = None
):
    """Возвращает QuerySet активных сотрудников из разрешенного списка должностей в зависимости от прав доступа.

    Фильтрует сотрудников с учетом division_affiliation должности (Летный / Инженерный / Общий состав).
    При передаче extra_user_id гарантирует включение указанного сотрудника (например, при редактировании существующей записи),
    исключая несовместимость QuerySet и ошибку "Cannot combine a unique query with a non-unique query".

    Args:
        user (Optional[DataBaseUser]): Текущий пользователь системы для фильтрации по правам доступа.
        target_scope (Optional[str]): Явный код категории ('0', '1', '2'), переопределяющий автоматический scope.
        extra_user_id (Optional[int]): Первичный ключ сотрудника для обязательного включения в выборку.

    Returns:
        QuerySet[DataBaseUser]: Отфильтрованный список сотрудников с предзагрузкой профилей и должностей.
    """
    from customers_app.models import DataBaseUser
    from django.db.models import Q

    scope = target_scope if target_scope is not None else get_user_personnel_scope(user)

    if scope == '1':
        # Только летный состав
        q_filter = (
            Q(user_work_profile__job__division_affiliation__pk=2)
            | Q(user_work_profile__job__division_affiliation__name="Летный состав")
            | Q(user_work_profile__job__type_of_job='1')
            | Q(user_work_profile__job__name__in=FLIGHT_CREW_JOB_NAMES)
        )
    elif scope == '2':
        # Только инженерный состав
        q_filter = (
            Q(user_work_profile__job__division_affiliation__pk=3)
            | Q(user_work_profile__job__division_affiliation__name="Инженерный состав")
            | Q(user_work_profile__job__type_of_job='2')
            | Q(user_work_profile__job__name__in=ENGINEERING_STAFF_JOB_NAMES)
        )
    else:
        # Все профильные сотрудники (летный + инженерный + общий)
        q_filter = (
            Q(user_work_profile__job__division_affiliation__pk__in=[1, 2, 3])
            | Q(user_work_profile__job__type_of_job__in=['0', '1', '2'])
            | Q(user_work_profile__job__name__in=ALL_STAFF_JOB_NAMES)
        )

    base_filter = Q(is_active=True, user_work_profile__isnull=False) & q_filter
    if extra_user_id:
        final_filter = base_filter | Q(pk=extra_user_id)
    else:
        final_filter = base_filter

    return DataBaseUser.objects.filter(
        final_filter
    ).select_related(
        'user_work_profile',
        'user_work_profile__job',
        'user_work_profile__job__division_affiliation'
    ).distinct().order_by('last_name', 'first_name')



EXACT_JOB_SHORTCUTS = {
    # Летный состав (с сохранением типа ВС)
    "командир воздушного судна ми-8": "КВС Ми-8",
    "командир воздушного судна": "КВС",
    "командир вс ми-8": "КВС Ми-8",
    "командир вс": "КВС",
    "второй пилот воздушного судна ми-8": "ВП Ми-8",
    "второй пилот воздушного судна": "ВП",
    "второй пилот вс ми-8": "ВП Ми-8",
    "второй пилот вс": "ВП",
    "второй пилот": "ВП",
    "пилот-инструктор воздушного судна ми-8": "Пилот-инструктор Ми-8",
    "пилот-инструктор вс ми-8": "Пилот-инструктор Ми-8",
    "пилот-инструктор воздушного судна": "Пилот-инструктор",
    "пилот-инструктор": "Пилот-инструктор",
    "пилот-инспектор по бп": "Пилот-инспектор БП",
    "пилот-инспектор по безопасности полетов": "Пилот-инспектор БП",
    "пилот-инспектор": "Пилот-инспектор",
    "бортовой механик воздушного судна ми-8": "Бортмеханик Ми-8",
    "бортовой механик вс ми-8": "Бортмеханик Ми-8",
    "бортовой механик": "Бортмеханик",
    "бортмеханик воздушного судна ми-8": "Бортмеханик Ми-8",
    "бортмеханик вс ми-8": "Бортмеханик Ми-8",
    "бортмеханик": "Бортмеханик",
    "бортмеханик-инструктор воздушного судна ми-8": "БМ-инструктор Ми-8",
    "бортмеханик-инструктор вс ми-8": "БМ-инструктор Ми-8",
    "бортмеханик-инструктор": "БМ-инструктор",
    "бортовой механик-инструктор": "БМ-инструктор",

    # Инженерно-технический состав
    "техник авиационный по эксплуатации вс": "Авиатехник по Э ВС",
    "техник авиационный по эксплуатации систем вс": "Авиатехник Э С ВС",
    "техник авиационный по экспл. систем вс": "Авиатехник Э С ВС",
    "техник авиационный": "Авиатехник",
    "авиационный техник": "Авиатехник",
    "инженер по эксплуатации вс": "Инженер по Э ВС",
    "ведущий инженер по эксплуатации вс": "Вед. инженер по Э ВС",
    "инженер по эксплуатации систем вс": "Инженер по Э С ВС",
    "ведущий инженер по эксплуатации систем вс": "Вед. инженер по Э С ВС",
    "инженер по качеству эксплуатации вс": "Инженер по качеству Э ВС",
    "инженер по качеству эксплуатации систем вс": "Инженер по качеству Э С ВС",
    "старший инженер по качеству эксплуатации вс": "Ст. инженер по качеству Э ВС",
    "старший инженер по качеству эксплуатации систем вс": "Ст. инженер по качеству Э С ВС",

    # Служба планирования и руководство
    "диспетчер по планированию полетов": "Диспетчер планирования",
    "диспетчер по планированию": "Диспетчер планирования",
    "летный директор / командир летного отряда": "Летный директор",
    "командир летного отряда": "Ком. летного отряда",
    "начальник летной службы": "Нач. летной службы",
    "заместитель командира летного отряда": "Зам. ком. летного отряда",
}

EXACT_JOB_ULTRA_SHORTCUTS = {
    "командир воздушного судна ми-8": "КВС",
    "командир воздушного судна": "КВС",
    "командир вс ми-8": "КВС",
    "командир вс": "КВС",
    "второй пилот воздушного судна ми-8": "ВП",
    "второй пилот воздушного судна": "ВП",
    "второй пилот вс ми-8": "ВП",
    "второй пилот вс": "ВП",
    "второй пилот": "ВП",
    "пилот-инструктор воздушного судна ми-8": "ПИ",
    "пилот-инструктор вс ми-8": "ПИ",
    "пилот-инструктор": "ПИ",
    "пилот-инспектор по бп": "ПИ по БП",
    "бортовой механик воздушного судна ми-8": "БМ",
    "бортовой механик вс ми-8": "БМ",
    "бортовой механик": "БМ",
    "бортмеханик воздушного судна ми-8": "БМ",
    "бортмеханик вс ми-8": "БМ",
    "бортмеханик": "БМ",
    "бортмеханик-инструктор воздушного судна ми-8": "БМ-инстр.",
    "бортмеханик-инструктор вс ми-8": "БМ-инстр.",
    "бортмеханик-инструктор": "БМ-инстр.",
    "бортовой механик-инструктор": "БМ-инстр.",
    "техник авиационный по эксплуатации вс": "Техник Э ВС",
    "техник авиационный по эксплуатации систем вс": "Техник Э С ВС",
    "техник авиационный": "Авиатехник",
    "инженер по эксплуатации вс": "Инженер Э ВС",
    "ведущий инженер по эксплуатации вс": "Вед. инженер Э ВС",
    "инженер по эксплуатации систем вс": "Инженер Э С ВС",
    "ведущий инженер по эксплуатации систем вс": "Вед. инженер Э С ВС",
    "инженер по качеству эксплуатации вс": "Инженер по качеству Э ВС",
    "старший инженер по качеству эксплуатации вс": "Ст. инженер по качеству Э ВС",
    "диспетчер по планированию полетов": "Диспетчер",
}


def format_short_job(job_name: Any, mode: str = 'standard') -> str:
    """Форматирует наименование должности сотрудника в краткий общепринятый авиационный вид.

    Применяет точные отраслевые аббревиатуры (напр. «Командир воздушного судна Ми-8» -> «КВС Ми-8»,
    «Второй пилот воздушного судна Ми-8» -> «2П Ми-8», «Бортмеханик-инструктор воздушного судна Ми-8» -> «Б/М-инструктор Ми-8»)
    с алгоритмическим fallback'ом для нестандартных должностей.

    Args:
        job_name (Any): Исходное наименование должности или объект Job.
        mode (str): Режим сокращения:
            - 'standard': Сохраняет тип ВС и ключевую специализацию (по умолчанию);
            - 'ultra': Максимально сжатый вид для компактных бейджей (напр. «КВС», «2П», «Б/М»).

    Returns:
        str: Краткое общепринятое наименование должности.
    """
    if not job_name:
        return ""

    raw_title = getattr(job_name, 'name', str(job_name)).strip()
    if not raw_title:
        return ""

    cleaned_lower = raw_title.lower()

    if mode == 'ultra':
        if cleaned_lower in EXACT_JOB_ULTRA_SHORTCUTS:
            return EXACT_JOB_ULTRA_SHORTCUTS[cleaned_lower]

    if cleaned_lower in EXACT_JOB_SHORTCUTS:
        return EXACT_JOB_SHORTCUTS[cleaned_lower]

    # Алгоритмический fallback для произвольных должностей
    result = raw_title
    replacements = [
        (r'\bвоздушного судна\b', 'ВС'),
        (r'\bвоздушных судов\b', 'ВС'),
        (r'\bпо эксплуатации\b', 'по Э'),
        (r'\bавиационный\b', 'авиа.'),
        (r'\bавиационная\b', 'авиа.'),
        (r'\bавиационные\b', 'авиа.'),
        (r'\bведущий\b', 'вед.'),
        (r'\bведущая\b', 'вед.'),
        (r'\bстарший\b', 'ст.'),
        (r'\bстаршая\b', 'ст.'),
        (r'\bзаместитель\b', 'зам.'),
        (r'\bинструктор\b', 'инстр.'),
        (r'\bначальник\b', 'нач.'),
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    return result.strip()


def get_periodic_check_type_merge_preview_service(
        source_type_id: int,
        target_type_id: int
) -> Dict[str, Any]:
    """Формирует предварительную сводку данных для объединения двух видов мероприятий.

    Args:
        source_type_id (int): Идентификатор исходного вида мероприятия (дубликата).
        target_type_id (int): Идентификатор целевого эталонного вида мероприятия.

    Returns:
        Dict[str, Any]: Словарь с метаданными и количеством затронутых записей:
            - 'status' (str): 'success' или 'error'.
            - 'source_type' (Dict[str, Any]): Параметры исходного вида.
            - 'target_type' (Dict[str, Any]): Параметры целевого вида.
            - 'records_count' (int): Количество переносимых записей в журнале.
            - 'assignments_count' (int): Количество индивидуальных закреплений за сотрудниками.
            - 'conflicting_assignments_count' (int): Количество уже существующих закреплений целевого вида.
    """
    from .models import PeriodicCheckType, PeriodicCheckRecord, EmployeeRequiredCheck

    if source_type_id == target_type_id:
        return {
            'status': 'error',
            'error': 'Нельзя объединить вид мероприятия сам с собой. Выберите разные виды.'
        }

    source_type = PeriodicCheckType.objects.select_related('aircraft_type').filter(id=source_type_id).first()
    target_type = PeriodicCheckType.objects.select_related('aircraft_type').filter(id=target_type_id).first()

    if not source_type:
        return {'status': 'error', 'error': f'Исходный вид мероприятия с ID #{source_type_id} не найден.'}
    if not target_type:
        return {'status': 'error', 'error': f'Целевой вид мероприятия с ID #{target_type_id} не найден.'}

    source_records = list(PeriodicCheckRecord.objects.filter(check_type=source_type))
    target_records_map = {
        (r.employee_id, r.aircraft_type_id, r.start_date, r.end_date): r
        for r in PeriodicCheckRecord.objects.filter(check_type=target_type)
    }

    records_count = len(source_records)
    records_duplicate_count = 0
    records_new_count = 0

    for src_rec in source_records:
        sig = (src_rec.employee_id, src_rec.aircraft_type_id, src_rec.start_date, src_rec.end_date)
        if sig in target_records_map:
            records_duplicate_count += 1
        else:
            records_new_count += 1

    source_assignments = set(EmployeeRequiredCheck.objects.filter(check_type=source_type).values_list('employee_id', flat=True))
    target_assignments = set(EmployeeRequiredCheck.objects.filter(check_type=target_type).values_list('employee_id', flat=True))

    conflicting_count = len(source_assignments.intersection(target_assignments))
    assignments_count = len(source_assignments)

    return {
        'status': 'success',
        'source_type': {
            'id': source_type.id,
            'name': source_type.name,
            'code': source_type.code or '',
            'aircraft_display': source_type.aircraft_display,
            'validity_months': source_type.validity_months,
            'validity_days': source_type.validity_days,
            'applies_to_display': source_type.get_applies_to_display(),
            'is_active': source_type.is_active
        },
        'target_type': {
            'id': target_type.id,
            'name': target_type.name,
            'code': target_type.code or '',
            'aircraft_display': target_type.aircraft_display,
            'validity_months': target_type.validity_months,
            'validity_days': target_type.validity_days,
            'applies_to_display': target_type.get_applies_to_display(),
            'is_active': target_type.is_active
        },
        'records_count': records_count,
        'records_new_count': records_new_count,
        'records_duplicate_count': records_duplicate_count,
        'assignments_count': assignments_count,
        'conflicting_assignments_count': conflicting_count
    }


def merge_periodic_check_types_service(
        source_type_id: int,
        target_type_id: int,
        delete_source: bool = True,
        user: Optional[Any] = None
) -> Dict[str, Any]:
    """Выполняет безопасное транзакционное объединение двух видов периодических мероприятий.

    Переносит все записи журнала (`PeriodicCheckRecord`) и индивидуальные
    закрепления (`EmployeeRequiredCheck`) с исходного вида (дубликата) на целевой эталонный вид.
    Интеллектуально дедуплицирует записи прохождения мероприятий:
    - Точные дубликаты записей (сотрудник, тип ВС, даты начала и окончания) склеиваются с дополнением
      отсутствующих реквизитов (номера документов, кем выдано, сканы) в целевую запись, а клон удаляется.
    - Новые сдачи и продления (отличные даты сдачи/срока действия) переносятся в целевой вид,
      автоматически становясь действующим статусом квалификации (по наивысшей дате окончания).
    Разрешает конфликты `unique_together` при переносе закреплений и удаляет/деактивирует дубликат.

    Args:
        source_type_id (int): Идентификатор объединяемого вида (дубликата).
        target_type_id (int): Идентификатор целевого эталонного вида мероприятия.
        delete_source (bool, optional): Флаг удаления исходного вида после слияния. Defaults to True.
        user (Optional[Any], optional): Пользователь, выполняющий операцию (для логирования).

    Returns:
        Dict[str, Any]: Результат слияния со статистикой:
            - 'status' (str): 'success' или 'error'.
            - 'source_name' (str): Наименование исходного вида.
            - 'target_name' (str): Наименование целевого вида.
            - 'records_transferred' (int): Количество перенесенных уникальных записей и продлений.
            - 'records_deduplicated' (int): Количество отброшенных/склеенных дубликатов записей.
            - 'assignments_transferred' (int): Количество перенесенных закреплений.
            - 'source_deleted' (bool): Флаг фактического удаления исходного вида.
            - 'message' (str): Описание успешного завершения.

    Raises:
        ValueError: При совпадении ID исходного и целевого вида.
    """
    import logging
    from django.db import transaction
    from .models import PeriodicCheckType, PeriodicCheckRecord, EmployeeRequiredCheck

    logger = logging.getLogger(__name__)

    if source_type_id == target_type_id:
        return {
            'status': 'error',
            'error': 'Нельзя объединить вид мероприятия сам с собой. Выберите разные виды.'
        }

    source_type = PeriodicCheckType.objects.filter(id=source_type_id).first()
    target_type = PeriodicCheckType.objects.filter(id=target_type_id).first()

    if not source_type:
        return {'status': 'error', 'error': f'Исходный вид мероприятия с ID #{source_type_id} не найден.'}
    if not target_type:
        return {'status': 'error', 'error': f'Целевой вид мероприятия с ID #{target_type_id} не найден.'}

    source_name = source_type.name
    target_name = target_type.name

    with transaction.atomic():
        # 1. Интеллектуальный перенос и дедупликация записей журнала мероприятий
        source_records = list(PeriodicCheckRecord.objects.filter(check_type=source_type))
        target_records_map = {
            (r.employee_id, r.aircraft_type_id, r.start_date, r.end_date): r
            for r in PeriodicCheckRecord.objects.filter(check_type=target_type)
        }

        records_transferred = 0
        records_deduplicated = 0

        for src_rec in source_records:
            sig = (src_rec.employee_id, src_rec.aircraft_type_id, src_rec.start_date, src_rec.end_date)
            if sig in target_records_map:
                # Точный дубликат: обогащаем целевую запись недостающими данными
                tgt_rec = target_records_map[sig]
                fields_to_update = []
                if not tgt_rec.document_number and src_rec.document_number:
                    tgt_rec.document_number = src_rec.document_number
                    fields_to_update.append('document_number')
                if not tgt_rec.issued_by and src_rec.issued_by:
                    tgt_rec.issued_by = src_rec.issued_by
                    fields_to_update.append('issued_by')
                if not tgt_rec.notes and src_rec.notes:
                    tgt_rec.notes = src_rec.notes
                    fields_to_update.append('notes')
                if not tgt_rec.scan_file and src_rec.scan_file:
                    tgt_rec.scan_file = src_rec.scan_file
                    fields_to_update.append('scan_file')

                if fields_to_update:
                    tgt_rec.save(update_fields=fields_to_update)

                # Удаляем избыточный дубликат
                src_rec.delete()
                records_deduplicated += 1
            else:
                # Новая запись / продление: перенаправляем на целевой вид
                src_rec.check_type = target_type
                src_rec.save(update_fields=['check_type'])
                target_records_map[sig] = src_rec
                records_transferred += 1

        # 2. Перенос индивидуальных закреплений за сотрудниками с защитой от unique_together
        source_assignments = list(EmployeeRequiredCheck.objects.filter(check_type=source_type))
        target_assignments_map = {
            a.employee_id: a for a in EmployeeRequiredCheck.objects.filter(check_type=target_type)
        }

        assignments_transferred = 0
        for src_assign in source_assignments:
            emp_id = src_assign.employee_id
            if emp_id in target_assignments_map:
                # У сотрудника уже есть закрепление целевого вида
                tgt_assign = target_assignments_map[emp_id]
                if src_assign.is_required and not tgt_assign.is_required:
                    tgt_assign.is_required = True
                    tgt_assign.save(update_fields=['is_required'])
                # Удаляем дублирующее закрепление
                src_assign.delete()
            else:
                # Перенаправляем закрепление на целевой вид
                src_assign.check_type = target_type
                src_assign.save(update_fields=['check_type'])
                target_assignments_map[emp_id] = src_assign

            assignments_transferred += 1

        # 3. Удаление или деактивация дубликата вида мероприятия
        if delete_source:
            source_type.delete()
            source_deleted = True
        else:
            source_type.is_active = False
            source_type.save(update_fields=['is_active'])
            source_deleted = False

    user_info = user.username if user else "system"
    logger.info(
        "Успешное объединение видов мероприятий [user=%s]: «%s» (#%s) -> «%s» (#%s). "
        "Перенесено/продлений: %s, склеено дублей: %s, закреплений: %s, удален: %s",
        user_info, source_name, source_type_id, target_name, target_type_id,
        records_transferred, records_deduplicated, assignments_transferred, source_deleted
    )

    msg = (
        f"Вид мероприятия «{source_name}» успешно объединен с «{target_name}». "
        f"Перенесено записей/продлений: {records_transferred}, исключено дубликатов: {records_deduplicated}, "
        f"закреплений сотрудников: {assignments_transferred}."
    )

    return {
        'status': 'success',
        'source_name': source_name,
        'target_name': target_name,
        'records_transferred': records_transferred,
        'records_deduplicated': records_deduplicated,
        'assignments_transferred': assignments_transferred,
        'source_deleted': source_deleted,
        'message': msg
    }


def get_lpc_roles_summary() -> Dict[str, Any]:
    """Формирует сводную информацию о текущих назначенных пользователях по ролевым группам ЛПК.

    Returns:
        Dict[str, Any]: Словарь с перечнем ролевых групп, описанием полномочий
            и списком активных пользователей.
    """
    from django.contrib.auth.models import Group
    from .permissions import (
        GROUP_LPC_MANAGEMENT,
        GROUP_LPC_FLIGHT_PLANNERS,
        GROUP_LPC_TECH_SERVICE,
        GROUP_LPC_FLIGHT_SERVICE,
        GROUP_LPC_HR_SAFETY,
        GROUP_LEGACY_PLANNERS,
        GROUP_COMPANY_LEADERSHIP,
    )

    role_definitions = [
        {
            'code': 'flight_planners',
            'group_name': GROUP_LPC_FLIGHT_PLANNERS,
            'legacy_name': GROUP_LEGACY_PLANNERS,
            'title': 'Диспетчеры планирования полетов',
            'description': 'Полное управление шахматкой экипажей, назначениями пилотов, формированием черновиков документов расстановки и контролем допусков летного состава.',
            'badge_class': 'badge-primary',
            'icon': 'bx-calendar-event',
        },
        {
            'code': 'tech_service',
            'group_name': GROUP_LPC_TECH_SERVICE,
            'legacy_name': None,
            'title': 'Инженерная служба (ИАС)',
            'description': 'Ведение журнала перемещений ВС (дислокация флота), учет периодических мероприятий и состояний инженерно-технического состава (авиатехников, инженеров ТО).',
            'badge_class': 'badge-warning',
            'icon': 'bxs-plane-take-off',
        },
        {
            'code': 'flight_service',
            'group_name': GROUP_LPC_FLIGHT_SERVICE,
            'legacy_name': None,
            'title': 'Летная служба / ЛМО',
            'description': 'Учет периодических мероприятий летного состава (ВЛЭК, тренажеры, проверки техники пилотирования, КПК) и состояний летчиков.',
            'badge_class': 'badge-info',
            'icon': 'bx-check-shield',
        },
        {
            'code': 'hr_safety',
            'group_name': GROUP_LPC_HR_SAFETY,
            'legacy_name': None,
            'title': 'Кадры и охрана труда',
            'description': 'Ведение общих периодических мероприятий (Охрана труда, ПБ, медицина) и общих состояний сотрудников.',
            'badge_class': 'badge-secondary',
            'icon': 'bx-user-check',
        },
        {
            'code': 'leadership',
            'group_name': GROUP_LPC_MANAGEMENT,
            'legacy_name': GROUP_COMPANY_LEADERSHIP,
            'title': 'Руководство компании (Наблюдатели)',
            'description': 'Сквозной просмотр всех данных, аналитики, отчетов и метеоцентра в режиме «Только чтение» + эксклюзивное право утверждать официальные документы расстановки.',
            'badge_class': 'badge-dark',
            'icon': 'bx-crown',
        },
    ]

    roles_data = []
    for r in role_definitions:
        group_names = [r['group_name']]
        if r['legacy_name']:
            group_names.append(r['legacy_name'])

        groups = Group.objects.filter(name__in=group_names)
        user_ids = set()
        users_list = []
        for g in groups:
            for u in g.user_set.filter(is_active=True).select_related('user_work_profile', 'user_work_profile__job'):
                if u.pk not in user_ids:
                    user_ids.add(u.pk)
                    users_list.append({
                        'id': u.pk,
                        'username': u.username,
                        'full_name': u.get_full_name() or u.username,
                        'job_title': u.user_work_profile.job.name if hasattr(u, 'user_work_profile') and u.user_work_profile and u.user_work_profile.job else '',
                    })

        roles_data.append({
            'code': r['code'],
            'group_name': r['group_name'],
            'title': r['title'],
            'description': r['description'],
            'badge_class': r['badge_class'],
            'icon': r['icon'],
            'users': users_list,
            'count': len(users_list),
        })

    return {'roles': roles_data}


def add_user_to_lpc_role(user_id: int, group_name: str, operator=None) -> Tuple[bool, str]:
    """Добавляет сотрудника в указанную ролевую группу ЛПК.

    Args:
        user_id (int): Идентификатор пользователя.
        group_name (str): Наименование ролевой группы.
        operator (Optional[DataBaseUser]): Пользователь, выполняющий назначение.

    Returns:
        Tuple[bool, str]: Успешность операции и текстовое сообщение для пользователя.
    """
    from django.contrib.auth.models import Group
    from customers_app.models import DataBaseUser

    user = DataBaseUser.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        return False, "Сотрудник не найден или заблокирован."

    group, _ = Group.objects.get_or_create(name=group_name)
    if user.groups.filter(pk=group.pk).exists():
        return False, f"Сотрудник {user.get_full_name()} уже входит в роль «{group_name}»."

    user.groups.add(group)
    op_info = operator.username if operator else "система"
    logger.info("Пользователь %s добавил %s в роль ЛПК «%s»", op_info, user.username, group_name)
    return True, f"Сотрудник {user.get_full_name()} успешно добавлен в роль «{group_name}»."


def remove_user_from_lpc_role(user_id: int, group_name: str, operator=None) -> Tuple[bool, str]:
    """Исключает сотрудника из указанной ролевой группы ЛПК.

    Args:
        user_id (int): Идентификатор пользователя.
        group_name (str): Наименование ролевой группы.
        operator (Optional[DataBaseUser]): Пользователь, выполняющий исключение.

    Returns:
        Tuple[bool, str]: Успешность операции и текстовое сообщение.
    """
    from django.contrib.auth.models import Group
    from customers_app.models import DataBaseUser

    user = DataBaseUser.objects.filter(pk=user_id).first()
    if not user:
        return False, "Сотрудник не найден."

    group = Group.objects.filter(name=group_name).first()
    if not group or not user.groups.filter(pk=group.pk).exists():
        return False, f"Сотрудник не состоит в роли «{group_name}»."

    user.groups.remove(group)
    op_info = operator.username if operator else "система"
    logger.info("Пользователь %s исключил %s из роли ЛПК «%s»", op_info, user.username, group_name)
    return True, f"Сотрудник {user.get_full_name()} успешно исключен из роли «{group_name}»."


