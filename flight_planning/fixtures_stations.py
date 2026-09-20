"""Утилита первоначального наполнения справочника метеостанций (AviationWeatherStation).

Содержит актуальный эталонный реестр опорных сертифицированных аэродромных метеостанций РФ
с подтвержденными международными кодами ICAO, географическими координатами и высотами КТА (MSL).
"""

import logging
from typing import Any, Dict, List

from flight_planning.models import AviationWeatherStation

logger = logging.getLogger(__name__)

INITIAL_RUSSIAN_METAR_STATIONS: List[Dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # 1. ХМАО, ЯНАО и Тюменская область (Ключевые базы авиакомпании «Баркол»)
    # -------------------------------------------------------------------------
    {"icao_code": "USRR", "name": "Surgut", "name_ru": "Сургут", "region": "ХМАО — Югра", "latitude": 61.3439, "longitude": 73.4025, "elevation_msl_m": 61.0, "is_active": True},
    {"icao_code": "USNN", "name": "Nizhnevartovsk", "name_ru": "Нижневартовск", "region": "ХМАО — Югра", "latitude": 60.9494, "longitude": 76.4800, "elevation_msl_m": 54.0, "is_active": True},
    {"icao_code": "USRO", "name": "Noyabrsk", "name_ru": "Ноябрьск", "region": "ЯНАО", "latitude": 63.1856, "longitude": 75.3000, "elevation_msl_m": 140.0, "is_active": True},
    {"icao_code": "USHH", "name": "Khanty-Mansiysk", "name_ru": "Ханты-Мансийск", "region": "ХМАО — Югра", "latitude": 61.0289, "longitude": 69.0928, "elevation_msl_m": 43.0, "is_active": True},
    {"icao_code": "USDD", "name": "Salekhard", "name_ru": "Салехард", "region": "ЯНАО", "latitude": 66.5900, "longitude": 66.6000, "elevation_msl_m": 44.0, "is_active": True},
    {"icao_code": "USMU", "name": "Novy Urengoy", "name_ru": "Новый Уренгой", "region": "ЯНАО", "latitude": 66.0700, "longitude": 76.5200, "elevation_msl_m": 65.0, "is_active": True},
    {"icao_code": "USMM", "name": "Nadym", "name_ru": "Надым", "region": "ЯНАО", "latitude": 65.4800, "longitude": 72.7000, "elevation_msl_m": 19.0, "is_active": True},
    {"icao_code": "USRK", "name": "Kogalym", "name_ru": "Когалым", "region": "ХМАО — Югра", "latitude": 62.1961, "longitude": 74.5336, "elevation_msl_m": 67.0, "is_active": True},
    {"icao_code": "USDB", "name": "Bovanenkovo", "name_ru": "Бованенково", "region": "ЯНАО", "latitude": 70.3167, "longitude": 68.3333, "elevation_msl_m": 25.0, "is_active": True},
    {"icao_code": "USYT", "name": "Tarko-Sale", "name_ru": "Тарко-Сале", "region": "ЯНАО", "latitude": 64.9167, "longitude": 77.8167, "elevation_msl_m": 28.0, "is_active": True},
    {"icao_code": "USRN", "name": "Nefteyugansk", "name_ru": "Нефтеюганск", "region": "ХМАО — Югра", "latitude": 61.1000, "longitude": 72.6333, "elevation_msl_m": 40.0, "is_active": True},
    {"icao_code": "USNR", "name": "Raduzhny", "name_ru": "Радужный", "region": "ХМАО — Югра", "latitude": 62.1550, "longitude": 77.3300, "elevation_msl_m": 76.0, "is_active": True},
    {"icao_code": "USTR", "name": "Roshchino (Tyumen)", "name_ru": "Тюмень (Рощино)", "region": "Тюменская область", "latitude": 57.1706, "longitude": 65.3267, "elevation_msl_m": 114.0, "is_active": True},
    {"icao_code": "USTL", "name": "Plekhanovo (Tyumen)", "name_ru": "Тюмень (Плеханово)", "region": "Тюменская область", "latitude": 57.1333, "longitude": 65.4667, "elevation_msl_m": 85.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 2. Западная Сибирь и Красноярский край
    # -------------------------------------------------------------------------
    {"icao_code": "UNTT", "name": "Bogashevo (Tomsk)", "name_ru": "Томск (Богашево)", "region": "Томская область", "latitude": 56.3833, "longitude": 85.2167, "elevation_msl_m": 181.0, "is_active": True},
    {"icao_code": "UNNT", "name": "Tolmachevo (Novosibirsk)", "name_ru": "Новосибирск (Толмачево)", "region": "Новосибирская область", "latitude": 55.0125, "longitude": 82.6506, "elevation_msl_m": 111.0, "is_active": True},
    {"icao_code": "UNOO", "name": "Omsk Centralny", "name_ru": "Омск (Центральный)", "region": "Омская область", "latitude": 54.9667, "longitude": 73.3167, "elevation_msl_m": 95.0, "is_active": True},
    {"icao_code": "UNAA", "name": "Abakan", "name_ru": "Абакан", "region": "Республика Хакасия", "latitude": 53.7400, "longitude": 91.3850, "elevation_msl_m": 245.0, "is_active": True},
    {"icao_code": "UNBB", "name": "Barnaul", "name_ru": "Барнаул", "region": "Алтайский край", "latitude": 53.4333, "longitude": 83.5167, "elevation_msl_m": 255.0, "is_active": True},
    {"icao_code": "UNEE", "name": "Kemerovo", "name_ru": "Кемерово", "region": "Кемеровская область", "latitude": 55.2701, "longitude": 86.1072, "elevation_msl_m": 261.0, "is_active": True},
    {"icao_code": "UNWW", "name": "Novokuznetsk (Spichenkovo)", "name_ru": "Новокузнецк (Спиченково)", "region": "Кемеровская область", "latitude": 53.8108, "longitude": 86.8783, "elevation_msl_m": 308.0, "is_active": True},
    {"icao_code": "UNKL", "name": "Krasnoyarsk (Yemelyanovo)", "name_ru": "Красноярск (Емельяново)", "region": "Красноярский край", "latitude": 56.1730, "longitude": 92.4830, "elevation_msl_m": 287.0, "is_active": True},
    {"icao_code": "USSE", "name": "Severo-Eniseysk", "name_ru": "Северо-Енисейск", "region": "Красноярский край", "latitude": 60.3700, "longitude": 93.1800, "elevation_msl_m": 519.0, "is_active": True},
    {"icao_code": "UOOO", "name": "Norilsk (Alykel)", "name_ru": "Норильск (Алыкель)", "region": "Красноярский край", "latitude": 69.3111, "longitude": 87.3322, "elevation_msl_m": 175.0, "is_active": True},
    {"icao_code": "UOHH", "name": "Khatanga", "name_ru": "Хатанга", "region": "Красноярский край", "latitude": 71.9772, "longitude": 102.4664, "elevation_msl_m": 33.0, "is_active": True},
    {"icao_code": "UOII", "name": "Igarka", "name_ru": "Игарка", "region": "Красноярский край", "latitude": 67.4667, "longitude": 86.5667, "elevation_msl_m": 31.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 3. Республика Коми и Ненецкий АО
    # -------------------------------------------------------------------------
    {"icao_code": "UUYY", "name": "Syktyvkar", "name_ru": "Сыктывкар", "region": "Республика Коми", "latitude": 61.6467, "longitude": 50.8500, "elevation_msl_m": 103.0, "is_active": True},
    {"icao_code": "UUYH", "name": "Ukhta", "name_ru": "Ухта", "region": "Республика Коми", "latitude": 63.5650, "longitude": 53.8050, "elevation_msl_m": 141.0, "is_active": True},
    {"icao_code": "UUYS", "name": "Usinsk", "name_ru": "Усинск", "region": "Республика Коми", "latitude": 66.0000, "longitude": 57.3667, "elevation_msl_m": 95.0, "is_active": True},
    {"icao_code": "UUYW", "name": "Vorkuta", "name_ru": "Воркута", "region": "Республика Коми", "latitude": 67.4889, "longitude": 63.9900, "elevation_msl_m": 181.0, "is_active": True},
    {"icao_code": "ULAM", "name": "Naryan-Mar", "name_ru": "Нарьян-Мар", "region": "Ненецкий АО", "latitude": 67.6400, "longitude": 53.1200, "elevation_msl_m": 11.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 4. Восточная Сибирь, Якутия и Дальний Восток
    # -------------------------------------------------------------------------
    {"icao_code": "UECT", "name": "Talakan", "name_ru": "Талакан", "region": "Республика Саха (Якутия)", "latitude": 59.8800, "longitude": 111.0500, "elevation_msl_m": 380.0, "is_active": True},
    {"icao_code": "UERR", "name": "Mirny", "name_ru": "Мирный", "region": "Республика Саха (Якутия)", "latitude": 62.5347, "longitude": 114.0389, "elevation_msl_m": 352.0, "is_active": True},
    {"icao_code": "UEEE", "name": "Yakutsk", "name_ru": "Якутск", "region": "Республика Саха (Якутия)", "latitude": 62.0933, "longitude": 129.7719, "elevation_msl_m": 99.0, "is_active": True},
    {"icao_code": "UIII", "name": "Irkutsk", "name_ru": "Иркутск", "region": "Иркутская область", "latitude": 52.2680, "longitude": 104.3889, "elevation_msl_m": 511.0, "is_active": True},
    {"icao_code": "UIBB", "name": "Bratsk", "name_ru": "Братск", "region": "Иркутская область", "latitude": 56.3708, "longitude": 101.6986, "elevation_msl_m": 490.0, "is_active": True},
    {"icao_code": "UIAA", "name": "Chita (Kadala)", "name_ru": "Чита (Кадала)", "region": "Забайкальский край", "latitude": 52.0263, "longitude": 113.3056, "elevation_msl_m": 685.0, "is_active": True},
    {"icao_code": "UIUU", "name": "Ulan-Ude (Baikal)", "name_ru": "Улан-Удэ (Байкал)", "region": "Республика Бурятия", "latitude": 51.8333, "longitude": 107.6000, "elevation_msl_m": 515.0, "is_active": True},
    {"icao_code": "UHBB", "name": "Blagoveshchensk (Ignatyevo)", "name_ru": "Благовещенск (Игнатьево)", "region": "Амурская область", "latitude": 50.4254, "longitude": 127.4125, "elevation_msl_m": 195.0, "is_active": True},
    {"icao_code": "UHHH", "name": "Khabarovsk (Novy)", "name_ru": "Хабаровск (Новый)", "region": "Хабаровский край", "latitude": 48.5167, "longitude": 135.1667, "elevation_msl_m": 72.0, "is_active": True},
    {"icao_code": "UHMA", "name": "Anadyr (Ugolny)", "name_ru": "Анадырь (Угольный)", "region": "Чукотский АО", "latitude": 64.7833, "longitude": 177.5667, "elevation_msl_m": 62.0, "is_active": True},
    {"icao_code": "UHMD", "name": "Provideniya Bay", "name_ru": "Бухта Провидения", "region": "Чукотский АО", "latitude": 64.3781, "longitude": -173.2433, "elevation_msl_m": 3.0, "is_active": True},
    {"icao_code": "UHMM", "name": "Magadan (Sokol)", "name_ru": "Магадан (Сокол)", "region": "Магаданская область", "latitude": 59.9110, "longitude": 150.7204, "elevation_msl_m": 118.0, "is_active": True},
    {"icao_code": "UHPP", "name": "Petropavlovsk-Kamchatsky (Yelizovo)", "name_ru": "Петропавловск-Камчатский (Елизово)", "region": "Камчатский край", "latitude": 53.1679, "longitude": 158.4537, "elevation_msl_m": 40.0, "is_active": True},
    {"icao_code": "UHSS", "name": "Yuzhno-Sakhalinsk (Khomutovo)", "name_ru": "Южно-Сахалинск (Хомутово)", "region": "Сахалинская область", "latitude": 46.9500, "longitude": 142.7167, "elevation_msl_m": 31.0, "is_active": True},
    {"icao_code": "UHWW", "name": "Vladivostok (Knevichi)", "name_ru": "Владивосток (Кневичи)", "region": "Приморский край", "latitude": 43.3990, "longitude": 132.1480, "elevation_msl_m": 184.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 5. Урал и Приволжский федеральный округ
    # -------------------------------------------------------------------------
    {"icao_code": "USSS", "name": "Koltsovo (Yekaterinburg)", "name_ru": "Екатеринбург (Кольцово)", "region": "Свердловская область", "latitude": 56.7431, "longitude": 60.8027, "elevation_msl_m": 233.0, "is_active": True},
    {"icao_code": "USCC", "name": "Chelyabinsk (Balandino)", "name_ru": "Челябинск (Баландино)", "region": "Челябинская область", "latitude": 55.3058, "longitude": 61.5033, "elevation_msl_m": 234.0, "is_active": True},
    {"icao_code": "USCM", "name": "Magnitogorsk", "name_ru": "Магнитогорск", "region": "Челябинская область", "latitude": 53.3931, "longitude": 58.7557, "elevation_msl_m": 435.0, "is_active": True},
    {"icao_code": "USPP", "name": "Bolshoe Savino (Perm)", "name_ru": "Пермь (Большое Савино)", "region": "Пермский край", "latitude": 57.9144, "longitude": 56.0211, "elevation_msl_m": 123.0, "is_active": True},
    {"icao_code": "UWWW", "name": "Kurumoch (Samara)", "name_ru": "Самара (Курумоч)", "region": "Самарская область", "latitude": 53.5048, "longitude": 50.1643, "elevation_msl_m": 145.0, "is_active": True},
    {"icao_code": "UWUU", "name": "Ufa", "name_ru": "Уфа", "region": "Республика Башкортостан", "latitude": 54.5575, "longitude": 55.8744, "elevation_msl_m": 180.0, "is_active": True},
    {"icao_code": "UWKD", "name": "Kazan", "name_ru": "Казань", "region": "Республика Татарстан", "latitude": 55.6062, "longitude": 49.2787, "elevation_msl_m": 126.0, "is_active": True},
    {"icao_code": "UWGG", "name": "Strigino (Nizhny Novgorod)", "name_ru": "Нижний Новгород (Стригино)", "region": "Нижегородская область", "latitude": 56.2300, "longitude": 43.7842, "elevation_msl_m": 78.0, "is_active": True},
    {"icao_code": "UWPS", "name": "Saransk", "name_ru": "Саранск", "region": "Республика Мордовия", "latitude": 54.1244, "longitude": 45.2106, "elevation_msl_m": 218.0, "is_active": True},
    {"icao_code": "UWSS", "name": "Saratov (Gagarin)", "name_ru": "Саратов (Гагарин)", "region": "Саратовская область", "latitude": 51.7214, "longitude": 46.1772, "elevation_msl_m": 168.0, "is_active": True},
    {"icao_code": "UWOO", "name": "Orenburg Centralny", "name_ru": "Оренбург (Центральный)", "region": "Оренбургская область", "latitude": 51.7958, "longitude": 55.4578, "elevation_msl_m": 118.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 6. Северо-Западный регион
    # -------------------------------------------------------------------------
    {"icao_code": "ULLI", "name": "Pulkovo (St. Petersburg)", "name_ru": "Санкт-Петербург (Пулково)", "region": "Санкт-Петербург", "latitude": 59.8003, "longitude": 30.2625, "elevation_msl_m": 24.0, "is_active": True},
    {"icao_code": "ULAA", "name": "Talagi (Arkhangelsk)", "name_ru": "Архангельск (Талаги)", "region": "Архангельская область", "latitude": 64.5042, "longitude": 40.7278, "elevation_msl_m": 19.0, "is_active": True},
    {"icao_code": "ULMM", "name": "Murmansk", "name_ru": "Мурманск", "region": "Мурманская область", "latitude": 68.7833, "longitude": 32.7500, "elevation_msl_m": 51.0, "is_active": True},
    {"icao_code": "ULOO", "name": "Pskov (Kresty)", "name_ru": "Псков (Кресты)", "region": "Псковская область", "latitude": 57.7839, "longitude": 28.3956, "elevation_msl_m": 47.0, "is_active": True},
    {"icao_code": "ULPB", "name": "Besovets (Petrozavodsk)", "name_ru": "Петрозаводск (Бесовец)", "region": "Республика Карелия", "latitude": 61.8167, "longitude": 34.2667, "elevation_msl_m": 46.0, "is_active": True},
    {"icao_code": "UMKK", "name": "Khrabrovo (Kaliningrad)", "name_ru": "Калининград (Храброво)", "region": "Калининградская область", "latitude": 54.7000, "longitude": 20.6167, "elevation_msl_m": 21.0, "is_active": True},
    {"icao_code": "ULWC", "name": "Cherepovets (Botovo)", "name_ru": "Череповец (Ботово)", "region": "Вологодская область", "latitude": 59.2761, "longitude": 38.0189, "elevation_msl_m": 112.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 7. Центральный регион
    # -------------------------------------------------------------------------
    {"icao_code": "UUEE", "name": "Sheremetyevo (Moscow)", "name_ru": "Москва (Шереметьево)", "region": "Московская область", "latitude": 55.9726, "longitude": 37.4146, "elevation_msl_m": 190.0, "is_active": True},
    {"icao_code": "UUDD", "name": "Domodedovo (Moscow)", "name_ru": "Москва (Домодедово)", "region": "Московская область", "latitude": 55.4088, "longitude": 37.9063, "elevation_msl_m": 179.0, "is_active": True},
    {"icao_code": "UUWW", "name": "Vnukovo (Moscow)", "name_ru": "Москва (Внуково)", "region": "Москва", "latitude": 55.5915, "longitude": 37.2615, "elevation_msl_m": 209.0, "is_active": True},
    {"icao_code": "UUBW", "name": "Zhukovsky (Ramenskoye)", "name_ru": "Москва (Жуковский / Раменское)", "region": "Московская область", "latitude": 55.5528, "longitude": 38.1497, "elevation_msl_m": 111.0, "is_active": True},
    {"icao_code": "UUBC", "name": "Grabtsevo (Kaluga)", "name_ru": "Калуга (Грабцево)", "region": "Калужская область", "latitude": 54.5533, "longitude": 36.3694, "elevation_msl_m": 198.0, "is_active": True},
    {"icao_code": "UUDL", "name": "Tunoshna (Yaroslavl)", "name_ru": "Ярославль (Туношна)", "region": "Ярославская область", "latitude": 57.5607, "longitude": 40.1574, "elevation_msl_m": 87.0, "is_active": True},
    {"icao_code": "UUOB", "name": "Belgorod", "name_ru": "Белгород", "region": "Белгородская область", "latitude": 50.6438, "longitude": 36.5901, "elevation_msl_m": 224.0, "is_active": True},
    {"icao_code": "UUOK", "name": "Kursk (Vostochny)", "name_ru": "Курск (Восточный)", "region": "Курская область", "latitude": 51.7506, "longitude": 36.2956, "elevation_msl_m": 209.0, "is_active": True},
    {"icao_code": "UUOL", "name": "Lipetsk", "name_ru": "Липецк", "region": "Липецкая область", "latitude": 52.7000, "longitude": 39.5167, "elevation_msl_m": 176.0, "is_active": True},
    {"icao_code": "UUOO", "name": "Chertovitskoye (Voronezh)", "name_ru": "Воронеж (Чертовицкое)", "region": "Воронежская область", "latitude": 51.6500, "longitude": 39.2500, "elevation_msl_m": 157.0, "is_active": True},

    # -------------------------------------------------------------------------
    # 8. Южный и Северо-Кавказский федеральные округа
    # -------------------------------------------------------------------------
    {"icao_code": "URSS", "name": "Adler (Sochi)", "name_ru": "Сочи (Адлер)", "region": "Краснодарский край", "latitude": 43.4333, "longitude": 39.9000, "elevation_msl_m": 16.0, "is_active": True},
    {"icao_code": "URMM", "name": "Mineralnye Vody", "name_ru": "Минеральные Воды", "region": "Ставропольский край", "latitude": 44.2251, "longitude": 43.0819, "elevation_msl_m": 314.0, "is_active": True},
    {"icao_code": "URRP", "name": "Platov (Rostov-on-Don)", "name_ru": "Ростов-на-Дону (Платов)", "region": "Ростовская область", "latitude": 47.4939, "longitude": 39.9247, "elevation_msl_m": 71.0, "is_active": True},
    {"icao_code": "URKK", "name": "Pashkovsky (Krasnodar)", "name_ru": "Краснодар (Пашковский)", "region": "Краснодарский край", "latitude": 45.0333, "longitude": 39.1500, "elevation_msl_m": 34.0, "is_active": True},
    {"icao_code": "URKA", "name": "Vityazevo (Anapa)", "name_ru": "Анапа (Витязево)", "region": "Краснодарский край", "latitude": 44.8833, "longitude": 37.2833, "elevation_msl_m": 53.0, "is_active": True},
    {"icao_code": "URWW", "name": "Gumrak (Volgograd)", "name_ru": "Волгоград (Гумрак)", "region": "Волгоградская область", "latitude": 48.7878, "longitude": 44.3361, "elevation_msl_m": 147.0, "is_active": True},
    {"icao_code": "URWA", "name": "Narimanovo (Astrakhan)", "name_ru": "Астрахань (Нариманово)", "region": "Астраханская область", "latitude": 46.2856, "longitude": 47.9951, "elevation_msl_m": -20.0, "is_active": True},
    {"icao_code": "URWI", "name": "Elista", "name_ru": "Элиста", "region": "Республика Калмыкия", "latitude": 46.3739, "longitude": 44.3309, "elevation_msl_m": 150.0, "is_active": True},
    {"icao_code": "URMT", "name": "Shpakovskoye (Stavropol)", "name_ru": "Ставрополь (Шпаковское)", "region": "Ставропольский край", "latitude": 45.1167, "longitude": 42.0833, "elevation_msl_m": 453.0, "is_active": True},
    {"icao_code": "URMG", "name": "Severny (Grozny)", "name_ru": "Грозный (Северный)", "region": "Чеченская Республика", "latitude": 43.3500, "longitude": 45.6833, "elevation_msl_m": 124.0, "is_active": True},
    {"icao_code": "URML", "name": "Uytash (Makhachkala)", "name_ru": "Махачкала (Уйташ)", "region": "Республика Дагестан", "latitude": 42.8167, "longitude": 47.6500, "elevation_msl_m": 4.0, "is_active": True},
    {"icao_code": "URMN", "name": "Nalchik", "name_ru": "Нальчик", "region": "Кабардино-Балкарская Республика", "latitude": 43.5129, "longitude": 43.6366, "elevation_msl_m": 445.0, "is_active": True},
    {"icao_code": "URMO", "name": "Beslan (Vladikavkaz)", "name_ru": "Владикавказ (Беслан)", "region": "Республика Северная Осетия — Алания", "latitude": 43.2051, "longitude": 44.6066, "elevation_msl_m": 505.0, "is_active": True},
]

# Для обратной совместимости
INITIAL_RUSSIAN_STATIONS: List[Dict[str, Any]] = INITIAL_RUSSIAN_METAR_STATIONS


def seed_aviation_weather_stations() -> int:
    """Заполняет справочник AviationWeatherStation эталонным набором опорных аэродромов РФ.

    Returns:
        int: Количество созданных или обновленных записей метеостанций в БД.
    """
    count = 0
    for st in INITIAL_RUSSIAN_METAR_STATIONS:
        icao = st["icao_code"]
        AviationWeatherStation.objects.update_or_create(
            icao_code=icao,
            defaults=st,
        )
        count += 1

    logger.info("Успешно инициализирован справочник опорных метеостанций: %s записей", count)
    return count
