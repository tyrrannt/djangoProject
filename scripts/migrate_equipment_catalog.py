"""Скрипт начального наполнения и нормализации каталога оборудования и СИ ТО (ФАП-145).

Выполняет:
1. Создание базового каталога обобщенных наименований (EquipmentName);
2. Создание утвержденных типов/моделей СИ (EquipmentTypeModel) с метрологическими параметрами;
3. Первичное связывание имеющихся записей MaintenanceEquipment с нормализованными типами;
4. Идемпотентное наполнение эталонных физических экземпляров оборудования на МПД
   (Тюмень, Тобольск, Сургут, Мячково) для отладки умного подбора (Smart Allocation).
"""

from typing import Dict, Any, List
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoProject.settings")
import django
django.setup()

from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from hrdepartment_app.models import (
    EquipmentName,
    EquipmentTypeModel,
    MaintenanceEquipment,
    PlaceProductionActivity,
    EquipmentType,
    EquipmentOperationalStatus,
    EquipmentVerificationType,
    IntervalUnit,
)
from contracts_app.models import TypeProperty


CATALOG_DATA: List[Dict[str, Any]] = [
    {
        "name": "Ареометр",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Прибор для измерения плотности авиатоплива (керосин ТС-1, РТ) и специальных жидкостей.",
        "types": [
            {
                "name": "АЭ-1",
                "part_number": "АЭ-1 ГОСТ 18481-81",
                "arshin_type_number": "4124-74",
                "measurement_range": "1000...1060 кг/м³",
                "accuracy_class": "0.5",
                "default_interval_months": 12,
            },
            {
                "name": "АНТ-2",
                "part_number": "АНТ-2 ГОСТ 18481-81",
                "arshin_type_number": "4125-74",
                "measurement_range": "710...770 кг/м³",
                "accuracy_class": "0.5",
                "default_interval_months": 12,
            },
            {
                "name": "АЭТ-1",
                "part_number": "АЭТ-1 ГОСТ 18481-81",
                "arshin_type_number": "4124-74",
                "measurement_range": "1000...1060 кг/м³",
                "accuracy_class": "0.5",
                "default_interval_months": 12,
            },
        ],
    },
    {
        "name": "Амперметр",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Щитовой и переносной прибор измерения силы постоянного и переменного тока бортовой сети ВС.",
        "types": [
            {
                "name": "М42300",
                "part_number": "М42300 ТУ 25-04.3300-77",
                "arshin_type_number": "1425-72",
                "measurement_range": "0...30 А",
                "accuracy_class": "1.5",
                "default_interval_months": 12,
            },
            {
                "name": "М42100",
                "part_number": "М42100 ТУ 25-04.3300-77",
                "arshin_type_number": "1425-72",
                "measurement_range": "0...50 А",
                "accuracy_class": "1.5",
                "default_interval_months": 12,
            },
        ],
    },
    {
        "name": "Вольтметр",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Прибор контроля напряжения бортовой сети ВС и наземных источников питания.",
        "types": [
            {
                "name": "М42300 (В)",
                "part_number": "М42300/В",
                "arshin_type_number": "1425-72",
                "measurement_range": "0...30 В",
                "accuracy_class": "1.5",
                "default_interval_months": 12,
            },
            {
                "name": "В7-38",
                "part_number": "В7-38",
                "arshin_type_number": "8724-82",
                "measurement_range": "0.1 мВ...1000 В",
                "accuracy_class": "0.1",
                "default_interval_months": 12,
            },
        ],
    },
    {
        "name": "Манометр",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Прибор для замера давления в гидросистеме, воздушной системе и баллонах ВС.",
        "types": [
            {
                "name": "МТИ-1218",
                "part_number": "МТИ-1218",
                "arshin_type_number": "1844-63",
                "measurement_range": "0...16 МПа",
                "accuracy_class": "0.6",
                "default_interval_months": 12,
            },
            {
                "name": "МВ-100",
                "part_number": "МВ-100",
                "arshin_type_number": "2189-66",
                "measurement_range": "0...100 кгс/см²",
                "accuracy_class": "1.0",
                "default_interval_months": 12,
            },
            {
                "name": "МТИ-1216",
                "part_number": "МТИ-1216",
                "arshin_type_number": "1844-63",
                "measurement_range": "0...2.5 МПа",
                "accuracy_class": "0.6",
                "default_interval_months": 12,
            },
        ],
    },
    {
        "name": "Динамометрический ключ",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Прецизионный динамометрический инструмент для затяжки резьбовых соединений крепления агрегатов ВС.",
        "types": [
            {
                "name": "КД-100",
                "part_number": "КД-100",
                "arshin_type_number": "54823-13",
                "measurement_range": "20...100 Н·м",
                "accuracy_class": "±4%",
                "default_interval_months": 12,
            },
            {
                "name": "КД-200",
                "part_number": "КД-200",
                "arshin_type_number": "54823-13",
                "measurement_range": "40...200 Н·м",
                "accuracy_class": "±4%",
                "default_interval_months": 12,
            },
            {
                "name": "STAHLWILLE 730/20",
                "part_number": "730/20 Quick",
                "arshin_type_number": "60214-15",
                "measurement_range": "40...200 Н·м",
                "accuracy_class": "±4%",
                "default_interval_months": 12,
            },
        ],
    },
    {
        "name": "Весы платформенные",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Платформенные весы для взвешивания грузов, багажа и агрегатов ВС.",
        "types": [
            {
                "name": "ВПЭ-150",
                "part_number": "ВПЭ-150",
                "arshin_type_number": "48924-11",
                "measurement_range": "1...150 кг",
                "accuracy_class": "III средний",
                "default_interval_months": 12,
            }
        ],
    },
    {
        "name": "Весы подвесные (крановые / безмен)",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Подвесные динамометрические весы для определения веса навесного оборудования.",
        "types": [
            {
                "name": "ВК-500",
                "part_number": "ВК-500",
                "arshin_type_number": "51240-12",
                "measurement_range": "10...500 кг",
                "accuracy_class": "III",
                "default_interval_months": 12,
            }
        ],
    },
    {
        "name": "Ваттметр",
        "category": EquipmentType.MEASURING,
        "is_measuring_instrument": True,
        "description": "Прибор измерения мощности переменного тока.",
        "types": [
            {
                "name": "Д5004",
                "part_number": "Д5004",
                "arshin_type_number": "3124-72",
                "measurement_range": "0...1000 Вт",
                "accuracy_class": "0.5",
                "default_interval_months": 12,
            }
        ],
    },
    {
        "name": "Аттенюатор",
        "category": EquipmentType.CONTROL_TEST,
        "is_measuring_instrument": True,
        "description": "Калиброванный поглотитель мощности для настройки радиоаппаратуры ВС.",
        "types": [
            {
                "name": "Д2-28",
                "part_number": "Д2-28",
                "arshin_type_number": "5891-77",
                "measurement_range": "0...60 дБ",
                "accuracy_class": "±0.5 дБ",
                "default_interval_months": 12,
            }
        ],
    },
    {
        "name": "Контрольно-поверочная аппаратура ПВД (КПА-ПВД)",
        "category": EquipmentType.CONTROL_TEST,
        "is_measuring_instrument": True,
        "description": "Установка проверки систем статического и динамического давления ВС (альтиметры, вариометры, УС).",
        "types": [
            {
                "name": "КПА-ПВД-1",
                "part_number": "КПА-ПВД-1М",
                "arshin_type_number": "12984-91",
                "measurement_range": "0...1000 км/ч, 0...12000 м",
                "accuracy_class": "0.5",
                "default_interval_months": 12,
            }
        ],
    },
    {
        "name": "Струбцина швартовки и фиксации лопастей несущего винта",
        "category": EquipmentType.SPECIAL_TOOL,
        "is_measuring_instrument": False,
        "description": "Специальный инструмент для фиксации лопастей НВ при стоянке и ТО (поверка не требуется).",
        "types": [
            {
                "name": "8АТ-9911-00",
                "part_number": "8АТ-9911-00",
                "arshin_type_number": "",
                "measurement_range": "Ми-8Т / Ми-8МТВ",
                "accuracy_class": "—",
                "default_interval_months": 0,
            }
        ],
    },
]


def populate_catalog() -> None:
    """Создает каталоги EquipmentName и EquipmentTypeModel и привязывает физические приборы."""
    print("=== Начало миграции каталога оборудования и СИ ТО (ФАП-145) ===")

    created_names = 0
    created_types = 0

    with transaction.atomic():
        for item in CATALOG_DATA:
            eq_name, name_created = EquipmentName.objects.get_or_create(
                name=item["name"],
                defaults={
                    "category": item["category"],
                    "is_measuring_instrument": item["is_measuring_instrument"],
                    "description": item["description"],
                },
            )
            if name_created:
                created_names += 1
                print(f"[+] Создано наименование: {eq_name.name}")

            for t_item in item["types"]:
                type_obj, t_created = EquipmentTypeModel.objects.get_or_create(
                    equipment_name=eq_name,
                    name=t_item["name"],
                    defaults={
                        "part_number": t_item["part_number"],
                        "arshin_type_number": t_item.get("arshin_type_number", ""),
                        "measurement_range": t_item.get("measurement_range", ""),
                        "accuracy_class": t_item.get("accuracy_class", ""),
                        "default_interval_months": t_item.get("default_interval_months", 12),
                    },
                )
                if t_created:
                    created_types += 1
                    print(f"    └── [+] Создан тип/модель: {eq_name.name} {type_obj.name}")

    print(f"\nИтог создания НСИ: Наименований создано: {created_names}, Типов создано: {created_types}")

    # Нормализуем физические экземпляры MaintenanceEquipment
    populate_sample_physical_equipment()


def populate_sample_physical_equipment() -> None:
    """Создает тестовые физические приборы на МПД Тюмень, Тобольск, Сургут, Мячково."""
    today = timezone.now().date()
    mpd_tyumen = PlaceProductionActivity.objects.filter(name__icontains="Тюмень").first()
    mpd_tobolsk = PlaceProductionActivity.objects.filter(name__icontains="Тобольск").first()
    mpd_surgut = PlaceProductionActivity.objects.filter(name__icontains="Сургут").first()
    mpd_myachkovo = PlaceProductionActivity.objects.filter(name__icontains="Мячково").first()

    if not mpd_tyumen:
        mpd_tyumen = PlaceProductionActivity.objects.create(
            name="Аэропорт Плеханово (Тюмень)",
            short_name="Тюмень (Плеханово)",
            latitude=57.1422,
            longitude=65.4811,
        )
    if not mpd_tobolsk:
        mpd_tobolsk = PlaceProductionActivity.objects.create(
            name="Аэропорт Ремезов (Тобольск)",
            short_name="Тобольск (Ремезов)",
            latitude=58.1314,
            longitude=68.3283,
        )
    if not mpd_surgut:
        mpd_surgut = PlaceProductionActivity.objects.create(
            name="Аэропорт Сургут",
            short_name="Сургут",
            latitude=61.3439,
            longitude=73.4072,
        )
    if not mpd_myachkovo:
        mpd_myachkovo = PlaceProductionActivity.objects.create(
            name="Аэродром Мячково",
            short_name="Мячково",
            latitude=55.5600,
            longitude=37.9839,
        )

    areometer_ae1 = EquipmentTypeModel.objects.filter(equipment_name__name="Ареометр", name="АЭ-1").first()
    areometer_ant2 = EquipmentTypeModel.objects.filter(equipment_name__name="Ареометр", name="АНТ-2").first()
    ammeter_m42300 = EquipmentTypeModel.objects.filter(equipment_name__name="Амперметр", name="М42300").first()
    voltmeter_v738 = EquipmentTypeModel.objects.filter(equipment_name__name="Вольтметр", name="В7-38").first()
    manometer_mti = EquipmentTypeModel.objects.filter(equipment_name__name="Манометр", name="МТИ-1218").first()
    wrench_kd100 = EquipmentTypeModel.objects.filter(equipment_name__name="Динамометрический ключ", name="КД-100").first()
    clamp_mi8 = EquipmentTypeModel.objects.filter(equipment_name__name="Струбцина швартовки и фиксации лопастей несущего винта").first()

    sample_instances = [
        # Тюмень
        {
            "type_model": areometer_ae1,
            "serial_number": "ИР-О-222",
            "inventory_number": "ИНВ-00142",
            "production_place": mpd_tyumen,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=90),
            "next_verification_date": today + timedelta(days=275),
            "arshin_verification_number": "С-ТЮМ/2026/8812",
        },
        {
            "type_model": ammeter_m42300,
            "serial_number": "АМ-771",
            "inventory_number": "ИНВ-00215",
            "production_place": mpd_tyumen,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=30),
            "next_verification_date": today + timedelta(days=335),
            "arshin_verification_number": "С-ТЮМ/2026/9014",
        },
        {
            "type_model": clamp_mi8,
            "serial_number": "СТР-001",
            "inventory_number": "ИНВ-00501",
            "production_place": mpd_tyumen,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.NOT_REQUIRED,
            "last_verification_date": None,
            "next_verification_date": None,
        },
        # Тобольск (донор близкий к Тюмени ~220 км)
        {
            "type_model": areometer_ae1,
            "serial_number": "1440",
            "inventory_number": "ИНВ-00143",
            "production_place": mpd_tobolsk,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=120),
            "next_verification_date": today + timedelta(days=245),
            "arshin_verification_number": "С-ТОБ/2026/1144",
        },
        {
            "type_model": manometer_mti,
            "serial_number": "МТ-992",
            "inventory_number": "ИНВ-00301",
            "production_place": mpd_tobolsk,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=60),
            "next_verification_date": today + timedelta(days=305),
            "arshin_verification_number": "С-ТОБ/2026/2201",
        },
        # Сургут (донор удаленный ~640 км)
        {
            "type_model": areometer_ant2,
            "serial_number": "331",
            "inventory_number": "ИНВ-00144",
            "production_place": mpd_surgut,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=200),
            "next_verification_date": today + timedelta(days=165),
            "arshin_verification_number": "С-СУР/2026/3310",
        },
        {
            "type_model": wrench_kd100,
            "serial_number": "КД-8841",
            "inventory_number": "ИНВ-00411",
            "production_place": mpd_surgut,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=40),
            "next_verification_date": today + timedelta(days=325),
            "arshin_verification_number": "С-СУР/2026/5521",
        },
        # Мячково (Москва)
        {
            "type_model": voltmeter_v738,
            "serial_number": "В7-0091",
            "inventory_number": "ИНВ-00288",
            "production_place": mpd_myachkovo,
            "operational_status": EquipmentOperationalStatus.SERVICEABLE,
            "verification_type": EquipmentVerificationType.VERIFICATION,
            "last_verification_date": today - timedelta(days=15),
            "next_verification_date": today + timedelta(days=350),
            "arshin_verification_number": "С-МСК/2026/0122",
        },
    ]

    with transaction.atomic():
        created_inst = 0
        for inst in sample_instances:
            if not inst["type_model"]:
                continue
            obj, created = MaintenanceEquipment.objects.get_or_create(
                serial_number=inst["serial_number"],
                defaults={
                    "type_model": inst["type_model"],
                    "name": f"{inst['type_model'].equipment_name.name} {inst['type_model'].name}",
                    "inventory_number": inst["inventory_number"],
                    "production_place": inst["production_place"],
                    "operational_status": inst["operational_status"],
                    "verification_type": inst["verification_type"],
                    "last_verification_date": inst["last_verification_date"],
                    "next_verification_date": inst["next_verification_date"],
                    "arshin_verification_number": inst.get("arshin_verification_number", ""),
                },
            )
            if created:
                created_inst += 1
                print(f"[+] Создан физический экземпляр: {obj.name} (S/N: {obj.serial_number}) на МПД '{obj.production_place}'")

    print(f"Итог: создано физических экземпляров оборудования: {created_inst}")
    print("=== Миграция каталога успешно завершена ===")


if __name__ == "__main__":
    populate_catalog()
