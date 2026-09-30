"""Интеллектуальная команда наполнения и сопоставления периодических регламентных работ.

Выполняет безопасное сопоставление и обновление записей PeriodicWork:
1. Точное обновление существующих записей с привязанным типом ВС;
2. Интеллектуальный поиск старых записей без типа ВС (air_bord_type IS NULL):
   - по используемым бортам в картах-нарядах (OutfitCard);
   - по уникальности кода регламента в таблице ТО;
3. Создание недостающих записей;
4. Поддержка режима симуляции (--dry-run).
"""

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple
from django.core.management.base import BaseCommand
from django.db import transaction
from contracts_app.models import TypeProperty
from hrdepartment_app.models import PeriodicWork, PeriodicWorkColor


PERIODIC_WORKS_DATA: List[Tuple[str, str, float, int, int, str]] = [
    # Cessna
    ("Cessna", "100 часов", 100.0, 10, 10, PeriodicWorkColor.YELLOW),
    ("Cessna", "400 часов", 400.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "500 часов", 500.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "1000 часов", 1000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "2000 часов", 2000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "3000 часов", 3000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "6000 часов", 6000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "10000 часов", 10000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("Cessna", "12000 часов", 12000.0, 10, 10, PeriodicWorkColor.GREEN),

    # R-44
    ("R-44", "50 часов", 50.0, 10, 10, PeriodicWorkColor.YELLOW),
    ("R-44", "100 часов", 100.0, 10, 10, PeriodicWorkColor.YELLOW),
    ("R-44", "300 часов", 300.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "500 часов", 500.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "600 часов", 600.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "900 часов", 900.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "1000 часов", 1000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "1200 часов", 1200.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "1500 часов", 1500.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "1800 часов", 1800.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-44", "2200 часов", 2000.0, 0, 0, PeriodicWorkColor.RED),
    ("R-44", "2000 часов", 2000.0, 10, 10, PeriodicWorkColor.GREEN),

    # R-66
    ("R-66", "100 часов", 100.0, 10, 10, PeriodicWorkColor.YELLOW),
    ("R-66", "400 часов", 400.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "600 часов", 600.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "800 часов", 800.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "1000 часов", 1000.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "1200 часов", 1200.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "1600 часов", 1600.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "1800 часов", 1800.0, 10, 10, PeriodicWorkColor.GREEN),
    ("R-66", "2000 часов", 2000.0, 5, 0, PeriodicWorkColor.RED),

    # Ан-2
    ("Ан-2", "100 часов", 100.0, 15, 15, PeriodicWorkColor.YELLOW),
    ("Ан-2", "400 часов", 400.0, 30, 30, PeriodicWorkColor.GREEN),
    ("Ан-2", "800 часов", 800.0, 30, 30, PeriodicWorkColor.GREEN),
    ("Ан-2", "1200 часов", 1200.0, 30, 30, PeriodicWorkColor.GREEN),
    ("Ан-2", "1600 часов", 1600.0, 30, 30, PeriodicWorkColor.GREEN),
    ("Ан-2", "2000 часов", 2000.0, 0, 0, PeriodicWorkColor.RED),

    # Ми-8 (Ф-1 .. Ф-59, КВР)
    ("Ми-8", "Ф-1", 75.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-2", 150.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-3", 225.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-4", 300.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-5", 375.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-6", 450.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-7", 525.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-8", 600.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-9", 675.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-10", 750.0, 20, 20, PeriodicWorkColor.GREEN),
    ("Ми-8", "Ф-11", 825.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-12", 900.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-13", 975.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-14", 1050.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-15", 1125.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-16", 1200.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-17", 1275.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-18", 1350.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-19", 1425.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-20", 1500.0, 20, 20, PeriodicWorkColor.GREEN),
    ("Ми-8", "Ф-21", 1575.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-22", 1650.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-23", 1725.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-24", 1800.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-25", 1875.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-26", 1950.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-27", 2025.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-28", 2100.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-29", 2175.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-30", 2250.0, 20, 20, PeriodicWorkColor.GREEN),
    ("Ми-8", "Ф-31", 2325.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-32", 2400.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-33", 2475.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-34", 2550.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-35", 2625.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-36", 2700.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-37", 2775.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-38", 2850.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-39", 2925.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-40", 3000.0, 20, 20, PeriodicWorkColor.GREEN),
    ("Ми-8", "Ф-41", 3075.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-42", 3150.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-43", 3225.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-44", 3300.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-45", 3375.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-46", 3450.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-47", 3525.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-48", 3600.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-49", 3675.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-50", 3750.0, 20, 20, PeriodicWorkColor.GREEN),
    ("Ми-8", "Ф-51", 3825.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-52", 3900.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-53", 3975.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-54", 4050.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-55", 4125.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-56", 4200.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-57", 4275.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-58", 4350.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "Ф-59", 4425.0, 20, 20, PeriodicWorkColor.YELLOW),
    ("Ми-8", "КВР", 4500.0, 10, 0, PeriodicWorkColor.RED),
]


class Command(BaseCommand):
    """Команда для создания или обновления справочника периодических работ."""

    help = "Инициализирует и интеллектуально сопоставляет записи PeriodicWork для ВС"

    def add_arguments(self, parser: Any) -> None:
        """Регистрирует аргументы командной строки."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Выполнить симуляцию без сохранения изменений в базе данных",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа в команду управления.

        Args:
            *args: Позиционные аргументы.
            **options: Именованные параметры, включая --dry-run.
        """
        dry_run: bool = options.get("dry_run", False)
        if dry_run:
            self.stdout.write(self.style.WARNING("--- РЕЖИМ СИМУЛЯЦИИ (--dry-run) ВКЛЮЧЕН ---"))

        self.stdout.write("Определение типов воздушных судов...")
        type_mapping: Dict[str, TypeProperty] = {}

        types_query = {
            "Cessna": TypeProperty.objects.filter(type_property__icontains="Cessna").first(),
            "R-44": TypeProperty.objects.filter(type_property__iexact="R-44").first(),
            "R-66": TypeProperty.objects.filter(type_property__iexact="R-66").first(),
            "Ан-2": (
                TypeProperty.objects.filter(type_property__icontains="АН-2").first()
                or TypeProperty.objects.filter(type_property__icontains="Ан-2").first()
            ),
            "Ми-8": (
                TypeProperty.objects.filter(type_property__icontains="МИ-8").first()
                or TypeProperty.objects.filter(type_property__icontains="Ми-8").first()
            ),
        }

        for key, type_obj in types_query.items():
            if type_obj:
                type_mapping[key] = type_obj
                self.stdout.write(self.style.SUCCESS(f"Тип ВС: '{key}' -> {type_obj} (ID: {type_obj.pk})"))
            else:
                self.stdout.write(self.style.WARNING(f"Не найден TypeProperty для '{key}', создание нового..."))
                if not dry_run:
                    type_mapping[key] = TypeProperty.objects.create(type_property=key)
                else:
                    type_mapping[key] = TypeProperty(type_property=key)

        # Вычисляем распределение кодов по типам ВС для определения уникальности кодов
        code_to_types: Dict[str, Set[str]] = defaultdict(set)
        for aircraft_key, code, _, _, _, _ in PERIODIC_WORKS_DATA:
            code_to_types[code].add(aircraft_key)

        stats = {
            "exact_updated": 0,
            "unlinked_matched_cards": 0,
            "unlinked_matched_unique": 0,
            "created_new": 0,
        }

        with transaction.atomic():
            for aircraft_key, code, ratio, lag_minus, lag_plus, color in PERIODIC_WORKS_DATA:
                type_prop = type_mapping[aircraft_key]
                work_name = f"{type_prop.type_property} - {code}"

                # 1. Уровень 1: Ищем точное совпадение по типу ВС и коду
                exact_match = PeriodicWork.objects.filter(
                    air_bord_type=type_prop,
                    code__iexact=code.strip(),
                ).first()

                if exact_match:
                    if not dry_run:
                        exact_match.name = work_name
                        exact_match.code = code
                        exact_match.ratio = ratio
                        exact_match.lag_minus = lag_minus
                        exact_match.lag_plus = lag_plus
                        exact_match.color = color
                        exact_match.save()
                    stats["exact_updated"] += 1
                    continue

                # 2. Уровень 2: Интеллектуальный поиск среди старых записей без типа ВС (air_bord_type IS NULL)
                unlinked_candidates = PeriodicWork.objects.filter(
                    air_bord_type__isnull=True,
                    code__iexact=code.strip(),
                )

                matched_candidate = None

                # 2.1 Проверка по картам-нарядам (OutfitCard)
                for candidate in unlinked_candidates:
                    has_card_for_type = candidate.outfit_card_periodic.filter(
                        air_board__type_property=type_prop
                    ).exists()
                    if has_card_for_type:
                        matched_candidate = candidate
                        stats["unlinked_matched_cards"] += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  [Карта-наряд] Найдена старая запись #{candidate.pk} '{candidate.code}', "
                                f"привязана к типу ВС '{type_prop}' по нарядам."
                            )
                        )
                        break

                # 2.2 Проверка по уникальности кода регламента (если код встречается только у одного типа ВС)
                if not matched_candidate and len(code_to_types[code]) == 1:
                    first_unlinked = unlinked_candidates.first()
                    if first_unlinked:
                        # Проверяем, что у нее нет карт с противоречащим другим типом ВС
                        has_conflict = first_unlinked.outfit_card_periodic.exclude(
                            air_board__type_property=type_prop
                        ).filter(air_board__type_property__isnull=False).exists()

                        if not has_conflict:
                            matched_candidate = first_unlinked
                            stats["unlinked_matched_unique"] += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  [Уникальный код] Старая запись #{first_unlinked.pk} '{code}' "
                                    f"привязана к единственному типу ВС '{type_prop}'."
                                )
                            )

                if matched_candidate:
                    if not dry_run:
                        matched_candidate.air_bord_type = type_prop
                        matched_candidate.name = work_name
                        matched_candidate.code = code
                        matched_candidate.ratio = ratio
                        matched_candidate.lag_minus = lag_minus
                        matched_candidate.lag_plus = lag_plus
                        matched_candidate.color = color
                        matched_candidate.save()
                    continue

                # 3. Уровень 3: Создаем новую запись, если совпадений не обнаружено
                if not dry_run:
                    PeriodicWork.objects.create(
                        name=work_name,
                        code=code,
                        ratio=ratio,
                        lag_minus=lag_minus,
                        lag_plus=lag_plus,
                        color=color,
                        air_bord_type=type_prop,
                    )
                stats["created_new"] += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nРезультат обработки ({'СИМУЛЯЦИЯ' if dry_run else 'ПРИМЕНЕНО'}):\n"
                f"  - Обновлено существующих (с типом ВС): {stats['exact_updated']}\n"
                f"  - Привязано старых записей по картам-нарядам: {stats['unlinked_matched_cards']}\n"
                f"  - Привязано старых записей по уникальности кода: {stats['unlinked_matched_unique']}\n"
                f"  - Создано новых записей: {stats['created_new']}\n"
                f"  - Всего записей в справочнике: {PeriodicWork.objects.count() if not dry_run else 'БД не изменена'}."
            )
        )
