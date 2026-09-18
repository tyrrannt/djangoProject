"""Тесты парсера авиационной метеорологии, сервисов и представлений (METAR / TAF)."""

from datetime import date, datetime, timezone as dt_timezone
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from .models import AviationWeatherForecast, AviationWeatherObservation
from .weather_services import MetarParser, TafParser, AviationWeatherService
from .views import mpd_weather_history_view, mpd_weather_widget_view, mpd_weather_refresh_view


class MetarParserTestCase(TestCase):
    """Набор тестов для парсера METAR и SPECI."""

    def test_parse_vfr_standard_mps(self):
        """Тест разбора стандартной сводки ПВП (VFR) с ветром в м/с."""
        raw = "METAR UNNT 181200Z 24005MPS 9999 BKN030 14/06 Q1018 NOSIG="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(parsed["icao_code"], "UNNT")
        self.assertEqual(parsed["report_type"], "METAR")
        self.assertEqual(parsed["wind_direction"], 240)
        self.assertEqual(parsed["wind_speed"], 5.0)
        self.assertIsNone(parsed["wind_gust"])
        self.assertFalse(parsed["wind_variable"])
        self.assertEqual(parsed["visibility_meters"], 10000)
        self.assertEqual(parsed["temperature"], 14.0)
        self.assertEqual(parsed["dew_point"], 6.0)
        self.assertEqual(parsed["pressure_hpa"], 1018.0)
        self.assertAlmostEqual(parsed["pressure_mmhg"], 763.6, places=1)
        # BKN030 = 3000 ft = 914.4 m -> VFR (> 914m and >=8000m)
        self.assertEqual(parsed["flight_category"], "VFR")

    def test_parse_calm_and_cavok(self):
        """Тест разбора штиля и условий CAVOK."""
        raw = "METAR UUEE 180600Z 00000MPS CAVOK 18/10 Q1015="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(parsed["icao_code"], "UUEE")
        self.assertEqual(parsed["wind_speed"], 0.0)
        self.assertTrue(parsed["cavok"])
        self.assertEqual(parsed["visibility_meters"], 10000)
        self.assertEqual(parsed["flight_category"], "VFR")

    def test_parse_knots_and_gusts(self):
        """Тест разбора сводки с ветром в узлах и порывами."""
        raw = "SPECI USRR 181530Z 18015G25KT 4000 -SHSN BKN015 M04/M08 Q0998="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(parsed["icao_code"], "USRR")
        self.assertEqual(parsed["report_type"], "SPECI")
        self.assertEqual(parsed["wind_direction"], 180)
        self.assertAlmostEqual(parsed["wind_speed"], 7.7, places=1)
        self.assertAlmostEqual(parsed["wind_gust"], 12.9, places=1)
        self.assertEqual(parsed["visibility_meters"], 4000)
        self.assertEqual(parsed["temperature"], -4.0)
        self.assertEqual(parsed["dew_point"], -8.0)
        self.assertEqual(parsed["pressure_hpa"], 998.0)
        self.assertIn("Слабый ливневый снег", parsed["weather_phenomena"])
        # Vis = 4000 m (between 1600 and 5000) -> IFR
        self.assertEqual(parsed["flight_category"], "IFR")

    def test_parse_lifr_low_ceiling_and_fog(self):
        """Тест условий низкой приборной погоды (LIFR / НППП) при густом тумане."""
        raw = "METAR ULLI 180300Z 04002MPS 0350 FZFG VV001 M01/M01 Q1022="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(parsed["icao_code"], "ULLI")
        self.assertEqual(parsed["visibility_meters"], 350)
        self.assertIn("Переохлажденный (замерзающий) туман", parsed["weather_phenomena"])
        # VV001 = 100 ft = 30.48 m -> LIFR (< 150m or vis < 1600m)
        self.assertEqual(parsed["flight_category"], "LIFR")

    def test_parse_variable_wind(self):
        """Тест переменного направления ветра (VRB)."""
        raw = "METAR USTR 180900Z VRB01MPS 8000 NSC 20/09 Q1012="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(parsed["icao_code"], "USTR")
        self.assertTrue(parsed["wind_variable"])
        self.assertIsNone(parsed["wind_direction"])
        self.assertEqual(parsed["wind_speed"], 1.0)
        self.assertEqual(parsed["visibility_meters"], 8000)
        # Vis = 8000 m -> MVFR
        self.assertEqual(parsed["flight_category"], "MVFR")

    def test_decode_weather_phenomena(self):
        """Тест декодирования авиационных метеокодов в русский текст."""
        self.assertEqual(MetarParser.decode_weather_phenomena("+TSRA"), "Сильный гроза с дождь")
        self.assertEqual(MetarParser.decode_weather_phenomena("-SN"), "Слабый снег")
        self.assertEqual(MetarParser.decode_weather_phenomena("FZFG"), "Переохлажденный (замерзающий) туман")
        self.assertEqual(MetarParser.decode_weather_phenomena("BLSN"), "Метель (низовая) снег")
        self.assertEqual(MetarParser.decode_weather_phenomena("BR"), "Дымка")


class TafParserTestCase(TestCase):
    """Набор тестов для парсера прогнозов TAF."""

    def test_parse_taf_standard(self):
        """Тест разбора типового прогноза TAF с группами изменений."""
        raw = "TAF UNNT 181100Z 1812/1918 24006MPS 9999 BKN020 TEMPO 1815/1821 3000 -SHSN BKN010="
        parsed = TafParser.parse_taf(raw)

        self.assertEqual(parsed["icao_code"], "UNNT")
        self.assertEqual(parsed["issued_at"].day, 18)
        self.assertEqual(parsed["issued_at"].hour, 11)
        self.assertEqual(parsed["valid_from"].day, 18)
        self.assertEqual(parsed["valid_from"].hour, 12)
        self.assertEqual(parsed["valid_to"].day, 19)
        self.assertEqual(parsed["valid_to"].hour, 18)
        self.assertGreaterEqual(parsed["forecast_json"]["total_periods"], 1)


class AviationWeatherServiceTestCase(TestCase):
    """Тесты сервиса сохранения и аналитики метеоданных."""

    def setUp(self):
        self.user = DataBaseUser.objects.create_user(
            username="test_weather_user",
            email="weather_test@barkol.ru",
            password="testpassword123",
            title="Тестовый Диспетчер",
        )
        self.mpd = PlaceProductionActivity.objects.create(
            name="МПД Толмачево",
            short_name="Толмачево",
            icao_code="UNNT",
            in_planning=True,
            weather_monitoring_enabled=True,
        )

    def test_sync_mpd_weather_saves_and_deduplicates(self):
        """Тест сохранения метеонаблюдения и предотвращения дубликатов."""
        raw_metar = "METAR UNNT 181200Z 24005MPS 9999 BKN030 14/06 Q1018="
        raw_taf = "TAF UNNT 181100Z 1812/1918 24006MPS 9999 BKN020="

        obs1, fc1 = AviationWeatherService.sync_mpd_weather(self.mpd, raw_metar=raw_metar, raw_taf=raw_taf)
        self.assertIsNotNone(obs1)
        self.assertIsNotNone(fc1)
        self.assertEqual(AviationWeatherObservation.objects.count(), 1)
        self.assertEqual(AviationWeatherForecast.objects.count(), 1)

        # Повторная синхронизация той же телеграммы должна обновить существующую запись без создания дубля
        obs2, fc2 = AviationWeatherService.sync_mpd_weather(self.mpd, raw_metar=raw_metar, raw_taf=raw_taf)
        self.assertEqual(AviationWeatherObservation.objects.count(), 1)
        self.assertEqual(AviationWeatherForecast.objects.count(), 1)
        self.assertEqual(obs1.pk, obs2.pk)

    def test_get_mpd_weather_timeline(self):
        """Тест выборки таймлайна метеонаблюдений и расчета суточной статистики."""
        now = timezone.now()
        today = now.date()

        # Создаем 2 наблюдения за сегодня
        t1 = datetime(today.year, today.month, today.day, 6, 0, tzinfo=dt_timezone.utc)
        t2 = datetime(today.year, today.month, today.day, 12, 0, tzinfo=dt_timezone.utc)

        AviationWeatherObservation.objects.create(
            mpd=self.mpd,
            icao_code="UNNT",
            observation_time=t1,
            report_type="METAR",
            raw_text="METAR UNNT 0600Z",
            flight_category="VFR",
            temperature=10.0,
            wind_speed=4.0,
            wind_gust=8.0,
            pressure_mmhg=760.0,
        )
        AviationWeatherObservation.objects.create(
            mpd=self.mpd,
            icao_code="UNNT",
            observation_time=t2,
            report_type="METAR",
            raw_text="METAR UNNT 1200Z",
            flight_category="VFR",
            temperature=16.0,
            wind_speed=6.0,
            wind_gust=12.0,
            pressure_mmhg=758.0,
        )

        timeline = AviationWeatherService.get_mpd_weather_timeline(self.mpd, today)
        self.assertEqual(len(timeline["observations"]), 2)
        stats = timeline["stats"]
        self.assertEqual(stats["min_temp"], 10.0)
        self.assertEqual(stats["max_temp"], 16.0)
        self.assertEqual(stats["max_wind"], 6.0)
        self.assertEqual(stats["max_gust"], 12.0)
        self.assertEqual(stats["min_pressure_mmhg"], 758.0)
        self.assertEqual(stats["max_pressure_mmhg"], 760.0)


class WeatherViewsTestCase(TestCase):
    """Тесты HTTP представлений метеоцентра МПД."""

    def setUp(self):
        self.user = DataBaseUser.objects.create_user(
            username="test_weather_viewer",
            email="viewer@barkol.ru",
            password="testpassword123",
            title="Инженер МТО",
        )
        self.mpd = PlaceProductionActivity.objects.create(
            name="МПД Сургут",
            short_name="Сургут",
            icao_code="USRR",
            in_planning=True,
            weather_monitoring_enabled=True,
        )
        self.client.force_login(self.user)

    def test_mpd_weather_history_view_get(self):
        """Тест отображения страницы истории погоды МПД."""
        url = reverse("flight_planning:mpd_weather_history", args=[self.mpd.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "МПД Сургут")
        self.assertContains(response, "USRR")

    def test_mpd_weather_widget_view_get(self):
        """Тест компактного виджета погоды."""
        url = reverse("flight_planning:mpd_weather_widget", args=[self.mpd.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_mpd_weather_refresh_api(self):
        """Тест эндпоинта принудительного обновления сводки."""
        url = reverse("flight_planning:mpd_weather_refresh", args=[self.mpd.pk])
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("icao_code"), "USRR")
