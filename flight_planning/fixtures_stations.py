"""Утилита первоначального наполнения справочника метеостанций (AviationWeatherStation)."""

import logging
from typing import Dict, List

from flight_planning.models import AviationWeatherStation

logger = logging.getLogger(__name__)

INITIAL_RUSSIAN_STATIONS: List[Dict[str, any]] = [
    # ХМАО и ЯНАО (Ключевые базы компании)
    {"icao_code": "USRR", "name": "Surgut", "name_ru": "Сургут", "latitude": 61.3439, "longitude": 73.4025, "elevation_msl_m": 61.0},
    {"icao_code": "USNN", "name": "Nizhnevartovsk", "name_ru": "Нижневартовск", "latitude": 60.9494, "longitude": 76.4800, "elevation_msl_m": 54.0},
    {"icao_code": "USRO", "name": "Noyabrsk", "name_ru": "Ноябрьск", "latitude": 63.1856, "longitude": 75.3000, "elevation_msl_m": 140.0},
    {"icao_code": "USMU", "name": "Novy Urengoy", "name_ru": "Новый Уренгой", "latitude": 66.0700, "longitude": 76.5200, "elevation_msl_m": 65.0},
    {"icao_code": "USHH", "name": "Khanty-Mansiysk", "name_ru": "Ханты-Мансийск", "latitude": 61.0289, "longitude": 69.0928, "elevation_msl_m": 43.0},
    {"icao_code": "USMM", "name": "Nadym", "name_ru": "Надым", "latitude": 65.4800, "longitude": 72.7000, "elevation_msl_m": 19.0},
    {"icao_code": "USDD", "name": "Salekhard", "name_ru": "Салехард", "latitude": 66.5900, "longitude": 66.6000, "elevation_msl_m": 44.0},
    {"icao_code": "USDB", "name": "Bovanenkovo", "name_ru": "Бованенково", "latitude": 70.3167, "longitude": 68.3333, "elevation_msl_m": 25.0},
    {"icao_code": "USYT", "name": "Tarko-Sale", "name_ru": "Тарко-Сале", "latitude": 64.9167, "longitude": 77.8167, "elevation_msl_m": 28.0},
    {"icao_code": "USRK", "name": "Kogalym", "name_ru": "Когалым", "latitude": 62.1961, "longitude": 74.5336, "elevation_msl_m": 67.0},
    {"icao_code": "USRN", "name": "Nefteyugansk", "name_ru": "Нефтеюганск", "latitude": 61.1000, "longitude": 72.6333, "elevation_msl_m": 40.0},
    {"icao_code": "USRA", "name": "Raduzhny", "name_ru": "Радужный", "latitude": 62.1550, "longitude": 77.3300, "elevation_msl_m": 76.0},
    {"icao_code": "USSE", "name": "Severo-Eniseysk", "name_ru": "Северо-Енисейск", "latitude": 60.3700, "longitude": 93.1800, "elevation_msl_m": 519.0},

    # Тюменская, Томская, Омская, Новосибирская обл.
    {"icao_code": "USTR", "name": "Roshchino (Tyumen)", "name_ru": "Тюмень (Рощино)", "latitude": 57.1706, "longitude": 65.3267, "elevation_msl_m": 114.0},
    {"icao_code": "USTL", "name": "Plekhanovo (Tyumen)", "name_ru": "Тюмень (Плеханово)", "latitude": 57.1333, "longitude": 65.4667, "elevation_msl_m": 85.0},
    {"icao_code": "UNTT", "name": "Bogashevo (Tomsk)", "name_ru": "Томск (Богашево)", "latitude": 56.3833, "longitude": 85.2167, "elevation_msl_m": 181.0},
    {"icao_code": "UNNT", "name": "Tolmachevo (Novosibirsk)", "name_ru": "Новосибирск (Толмачево)", "latitude": 55.0125, "longitude": 82.6506, "elevation_msl_m": 111.0},
    {"icao_code": "UNOO", "name": "Omsk Centralny", "name_ru": "Омск (Центральный)", "latitude": 54.9667, "longitude": 73.3167, "elevation_msl_m": 95.0},

    # Республика Коми и Ненецкий АО
    {"icao_code": "UUYY", "name": "Syktyvkar", "name_ru": "Сыктывкар", "latitude": 61.6467, "longitude": 50.8500, "elevation_msl_m": 103.0},
    {"icao_code": "UUYH", "name": "Ukhta", "name_ru": "Ухта", "latitude": 63.5650, "longitude": 53.8050, "elevation_msl_m": 141.0},
    {"icao_code": "UUUS", "name": "Usinsk", "name_ru": "Усинск", "latitude": 66.0000, "longitude": 57.3667, "elevation_msl_m": 95.0},
    {"icao_code": "UUYW", "name": "Vorkuta", "name_ru": "Воркута", "latitude": 67.4889, "longitude": 63.9900, "elevation_msl_m": 181.0},
    {"icao_code": "ULAM", "name": "Naryan-Mar", "name_ru": "Нарьян-Мар", "latitude": 67.6400, "longitude": 53.1200, "elevation_msl_m": 11.0},

    # Восточная Сибирь и Якутия
    {"icao_code": "UECT", "name": "Talakan", "name_ru": "Талакан", "latitude": 59.8800, "longitude": 111.0500, "elevation_msl_m": 380.0},
    {"icao_code": "UERR", "name": "Mirny", "name_ru": "Мирный", "latitude": 62.5347, "longitude": 114.0389, "elevation_msl_m": 352.0},
    {"icao_code": "UEEE", "name": "Yakutsk", "name_ru": "Якутск", "latitude": 62.0933, "longitude": 129.7719, "elevation_msl_m": 99.0},
    {"icao_code": "UIII", "name": "Irkutsk", "name_ru": "Иркутск", "latitude": 52.2680, "longitude": 104.3889, "elevation_msl_m": 511.0},
    {"icao_code": "UNKL", "name": "Krasnoyarsk (Yemelyanovo)", "name_ru": "Красноярск (Емельяново)", "latitude": 56.1730, "longitude": 92.4830, "elevation_msl_m": 287.0},

    # Центральный, Уральский и Приволжский регионы
    {"icao_code": "UUEE", "name": "Sheremetyevo (Moscow)", "name_ru": "Москва (Шереметьево)", "latitude": 55.9726, "longitude": 37.4146, "elevation_msl_m": 190.0},
    {"icao_code": "UUDD", "name": "Domodedovo (Moscow)", "name_ru": "Москва (Домодедово)", "latitude": 55.4088, "longitude": 37.9063, "elevation_msl_m": 179.0},
    {"icao_code": "UUWW", "name": "Vnukovo (Moscow)", "name_ru": "Москва (Внуково)", "latitude": 55.5915, "longitude": 37.2615, "elevation_msl_m": 209.0},
    {"icao_code": "ULLI", "name": "Pulkovo (St. Petersburg)", "name_ru": "Санкт-Петербург (Пулково)", "latitude": 59.8003, "longitude": 30.2625, "elevation_msl_m": 24.0},
    {"icao_code": "USSS", "name": "Koltsovo (Yekaterinburg)", "name_ru": "Екатеринбург (Кольцово)", "latitude": 56.7431, "longitude": 60.8027, "elevation_msl_m": 233.0},
    {"icao_code": "UWWW", "name": "Kurumoch (Samara)", "name_ru": "Самара (Курумоч)", "latitude": 53.5048, "longitude": 50.1643, "elevation_msl_m": 145.0},
    {"icao_code": "UWUU", "name": "Ufa", "name_ru": "Уфа", "latitude": 54.5575, "longitude": 55.8744, "elevation_msl_m": 180.0},
    {"icao_code": "UWKD", "name": "Kazan", "name_ru": "Казань", "latitude": 55.6062, "longitude": 49.2787, "elevation_msl_m": 126.0},
    {"icao_code": "USPP", "name": "Bolshoe Savino (Perm)", "name_ru": "Пермь (Большое Савино)", "latitude": 57.9144, "longitude": 56.0211, "elevation_msl_m": 123.0},
]


def seed_aviation_weather_stations() -> int:
    """Заполняет справочник AviationWeatherStation базовым набором опорных аэродромов РФ.

    Returns:
        int: Количество созданных/обновленных записей станций.
    """
    count = 0
    for st in INITIAL_RUSSIAN_STATIONS:
        icao = st["icao_code"]
        AviationWeatherStation.objects.update_or_create(
            icao_code=icao,
            defaults=st,
        )
        count += 1

    logger.info("Успешно инициализирован справочник опорных метеостанций: %s записей", count)
    return count
