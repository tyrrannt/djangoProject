# flight_planning/services.py
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from .models import PilotAssignment

def get_grouped_pilot_schedule(assignments: List[PilotAssignment], year: int, month: int) -> List[Dict[str, Any]]:
    """
    Groups pilot assignments into continuous date ranges, including gaps.

    Args:
        assignments: List of PilotAssignment instances, ordered by date.
        year: Target year.
        month: Target month.

    Returns:
        A list of dictionaries containing 'start_date', 'end_date', 'mpd_name', and 'is_gap'.
    """
    if not assignments and not (year and month):
        return []

    # Определяем границы месяца
    start_of_month = date(year, month, 1)
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

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
            grouped_schedule.append({
                'start_date': range_start,
                'end_date': current_date,
                'mpd_name': current_mpd_name,
                'is_gap': current_mpd_id is None,
                'days_count': (current_date - range_start).days + 1
            })
            
            # Начинаем новый диапазон
            range_start = next_date
            current_mpd_id = next_mpd_id
            current_mpd_name = next_mpd_name
            
        current_date = next_date

    return grouped_schedule
