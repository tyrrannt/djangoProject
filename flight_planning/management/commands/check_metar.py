"""Команда управления Django для проверки и диагностики авиационных метеоданных (METAR / TAF).

Позволяет проверить доступность сводок для любого 4-буквенного ICAO кода (латиница или кириллица),
просмотреть сырые ответы шлюза NOAA и расшифрованные летные параметры.

Пример использования:
    python manage.py check_metar URWW
    python manage.py check_metar USRR UNNT USTR
    python manage.py check_metar УРВВ --sync
"""

import sys
from typing import Any, List

from django.core.management.base import BaseCommand

from flight_planning.weather_services import AviationWeatherService, normalize_icao_code
from hrdepartment_app.models import PlaceProductionActivity


class Command(BaseCommand):
    """Команда проверки и диагностики метеорологических сводок METAR/TAF."""

    help = "Проверка и диагностика доступности сводок METAR / TAF по ICAO коду (например: python manage.py check_metar URWW)"

    def add_arguments(self, parser) -> None:
        """Регистрация аргументов командной строки."""
        parser.add_argument(
            "icao_codes",
            nargs="+",
            type=str,
            help="Один или несколько 4-буквенных ICAO кодов аэродромов (напр. URWW, USRR, UNNT, УРВВ)",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Автоматически сохранить полученные данные в базу для привязанных МПД",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Точка входа в выполнение команды."""
        icao_list: List[str] = options["icao_codes"]
        do_sync: bool = options["sync"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== ДИАГНОСТИКА АВИАЦИОННОЙ МЕТЕОРОЛОГИИ (NOAA / METAR / TAF) ==="))

        for raw_code in icao_list:
            norm_code = normalize_icao_code(raw_code)
            self.stdout.write(f"\n[+] Проверка кода: '{raw_code}' -> нормализованный ICAO: '{norm_code}'")

            diag = AviationWeatherService.diagnose_icao(raw_code)
            status = diag.get("diagnostic_status")

            if status == "invalid_format":
                self.stdout.write(self.style.ERROR(f"  [!] Ошибка формата: {diag['message']}"))
                continue

            # Ищем связанные МПД в базе
            matched_mpds = PlaceProductionActivity.objects.filter(icao_code__iexact=norm_code)
            if matched_mpds.exists():
                mpd_names = ", ".join([f"'{m.name}' (ID={m.pk})" for m in matched_mpds])
                self.stdout.write(self.style.SUCCESS(f"  [i] Привязанные МПД в системе: {mpd_names}"))
            else:
                self.stdout.write(self.style.WARNING(f"  [?] В базе данных МПД с ICAO-кодом '{norm_code}' пока не найдено"))

            # Выводим статус METAR
            if diag.get("has_metar"):
                self.stdout.write(self.style.SUCCESS(f"  [✓] METAR (фактическая погода) ПОЛУЧЕН:"))
                self.stdout.write(f"      RAW: {diag['metar_raw']}")

                pm = diag.get("parsed_metar")
                if pm:
                    cat = pm.get("flight_category", "—")
                    wind = f"{pm.get('wind_direction', 0)}° {pm.get('wind_speed', 0):.0f} м/с"
                    if pm.get("wind_gust"):
                        wind += f" (порывы {pm['wind_gust']:.0f} м/с)"
                    temp = f"{pm.get('temperature', 0):+.0f}°C" if pm.get("temperature") is not None else "—"
                    vis = f"{pm.get('visibility_meters', 0)} м" if pm.get("visibility_meters") is not None else "—"
                    cloud = f"{pm.get('cloud_base_meters', 0)} м ({pm.get('cloud_coverage', '')})" if pm.get("cloud_base_meters") is not None else "—"
                    press = f"{pm.get('pressure_mmhg', 0):.1f} мм рт.ст. ({pm.get('pressure_hpa', 0):.0f} гПа)" if pm.get("pressure_mmhg") else "—"
                    phenomena = pm.get("weather_phenomena") or "Без опасных явлений"

                    self.stdout.write(f"      - Летные условия: {cat}")
                    self.stdout.write(f"      - Ветер: {wind}")
                    self.stdout.write(f"      - Видимость: {vis} | НГО: {cloud}")
                    self.stdout.write(f"      - Температура: {temp} | Давление QNH: {press}")
                    self.stdout.write(f"      - Явления: {phenomena}")
            else:
                self.stdout.write(self.style.ERROR(f"  [✗] METAR: Не возвращен шлюзом NOAA"))

            # Выводим статус TAF
            if diag.get("has_taf"):
                self.stdout.write(self.style.SUCCESS(f"  [✓] TAF (прогноз аэродрома) ПОЛУЧЕН:"))
                self.stdout.write(f"      RAW: {diag['taf_raw']}")
            else:
                self.stdout.write(self.style.WARNING(f"  [✗] TAF: Прогноз отсутствует или не опубликован"))

            self.stdout.write(f"  [*] Заключение: {diag.get('message')}")

            # Если запрошена синхронизация
            if do_sync and matched_mpds.exists() and (diag.get("has_metar") or diag.get("has_taf")):
                for m in matched_mpds:
                    obs, fcast = AviationWeatherService.sync_mpd_weather(
                        m,
                        raw_metar=diag.get("metar_raw"),
                        raw_taf=diag.get("taf_raw"),
                    )
                    self.stdout.write(self.style.SUCCESS(f"  [+] Успешно сохранено в БД для МПД '{m.name}' (Замер: {obs}, Прогноз: {fcast})"))

        self.stdout.write("\n" + self.style.MIGRATE_HEADING("=== ДИАГНОСТИКА ЗАВЕРШЕНА ==="))
