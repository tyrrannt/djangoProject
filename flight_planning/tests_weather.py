"""Тесты парсера авиационной метеорологии, сервисов, координатных прогнозов и представлений."""

from datetime import date, datetime, timedelta, timezone as dt_timezone
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from .models import (
    AviationWeatherForecast,
    AviationWeatherObservation,
    AviationWeatherStation,
    CoordinateWeatherForecast,
    WMO_WEATHER_CODES,
)
from .weather_services import MetarParser, TafParser, AviationWeatherService
from .weather_providers.geo_service import GeoStationService
from .weather_providers.open_meteo_provider import OpenMeteoProvider
from .weather_providers.weather_manager import WeatherManagerService


class MetarParserTestCase(TestCase):
    """Набор тестов для парсера METAR и SPECI."""

    def test_parse_vfr_standard_mps(self):
        """Тест разбора стандартной сводки ПВП (VFR) с ветром в м/с и высоким потолком."""
        raw = "METAR UNNT 181200Z 24005MPS 9999 BKN040 14/06 Q1018 NOSIG="
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
        # BKN040 = 4000 ft = 1219 m -> VFR (> 914m and >= 8000m)
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
        self.assertEqual(MetarParser.decode_weather_phenomena("+TSRA"), "Сильный гроза дождь")
        self.assertEqual(MetarParser.decode_weather_phenomena("-SN"), "Слабый снег")
        self.assertEqual(MetarParser.decode_weather_phenomena("FZFG"), "Переохлажденный (замерзающий) туман")
        self.assertEqual(MetarParser.decode_weather_phenomena("BLSN"), "Метель (низовая) снег")
        self.assertEqual(MetarParser.decode_weather_phenomena("BR"), "Дымка")

    def test_parse_multiple_cloud_layers(self):
        """Тест извлечения множественных слоев облачности в cloud_layers."""
        raw = "METAR UUEE 181200Z 24005MPS 9999 FEW010 SCT025 BKN040CB 14/06 Q1018="
        parsed = MetarParser.parse_metar(raw)

        self.assertEqual(len(parsed["cloud_layers"]), 3)
        self.assertEqual(parsed["cloud_layers"][0]["coverage"], "FEW")
        self.assertEqual(parsed["cloud_layers"][0]["altitude_ft"], 1000)
        self.assertEqual(parsed["cloud_layers"][1]["coverage"], "SCT")
        self.assertEqual(parsed["cloud_layers"][1]["altitude_ft"], 2500)
        self.assertEqual(parsed["cloud_layers"][2]["coverage"], "BKN")
        self.assertEqual(parsed["cloud_layers"][2]["altitude_ft"], 4000)
        self.assertEqual(parsed["cloud_layers"][2]["type"], "CB")


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
            first_name="Иван",
            last_name="Иванов",
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
        raw_metar = "METAR UNNT 181200Z 24005MPS 9999 BKN040 14/06 Q1018="
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


class GeoStationServiceTestCase(TestCase):
    """Тесты гео-сервиса опорных станций (Haversine & delta H)."""

    def setUp(self):
        self.st_surgut = AviationWeatherStation.objects.create(
            icao_code="USRR",
            name="Surgut",
            name_ru="Сургут",
            latitude=61.3439,
            longitude=73.4025,
            elevation_msl_m=61.0,
            is_active=True,
        )
        self.st_nizhnevartovsk = AviationWeatherStation.objects.create(
            icao_code="USNN",
            name="Nizhnevartovsk",
            name_ru="Нижневартовск",
            latitude=60.9497,
            longitude=76.4800,
            elevation_msl_m=54.0,
            is_active=True,
        )

    def test_haversine_distance_calculation(self):
        """Тест расчета расстояния по формуле Haversine."""
        dist = GeoStationService.haversine_distance(
            self.st_surgut.latitude, self.st_surgut.longitude,
            self.st_nizhnevartovsk.latitude, self.st_nizhnevartovsk.longitude
        )
        self.assertGreater(dist, 160.0)
        self.assertLess(dist, 180.0)

    def test_find_nearest_station_for_mpd(self):
        """Тест нахождения ближайшей станции для МПД с координатами."""
        result = GeoStationService.find_nearest_station(
            latitude=61.50,
            longitude=73.50,
            mpd_elevation_msl_m=80.0,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["station"].icao_code, "USRR")
        self.assertLess(result["distance_km"], 40.0)
        # delta_h = 80 - 61 = 19 m
        self.assertEqual(result["elevation_delta_m"], 19.0)

    def test_distant_station_threshold(self):
        """Тест правила 15 км для репрезентативности опорной станции."""
        # Близкая точка (дистанция < 15 км от Сургута 61.3439, 73.4025)
        near_res = GeoStationService.find_nearest_station(
            latitude=61.35,
            longitude=73.42,
            mpd_elevation_msl_m=65.0,
        )
        self.assertIsNotNone(near_res)
        self.assertTrue(near_res["is_representative"])
        self.assertFalse(near_res["is_distant"])
        self.assertLessEqual(near_res["distance_km"], 15.0)

        # Удаленная точка (дистанция > 15 км от Сургута)
        far_res = GeoStationService.find_nearest_station(
            latitude=61.80,
            longitude=73.40,
            mpd_elevation_msl_m=80.0,
        )
        self.assertIsNotNone(far_res)
        self.assertFalse(far_res["is_representative"])
        self.assertTrue(far_res["is_distant"])
        self.assertGreater(far_res["distance_km"], 15.0)


class NoaaWeatherProviderTestCase(TestCase):
    """Тесты провайдера NOAA Aviation Weather Center."""

    def test_noaa_provider_normalize_icao(self):
        """Тест нормализации кодов станций ICAO в NoaaWeatherProvider."""
        from .weather_providers.noaa_provider import NoaaWeatherProvider
        self.assertEqual(NoaaWeatherProvider.normalize_icao_code("urww"), "URWW")
        self.assertEqual(NoaaWeatherProvider.normalize_icao_code("УРВВ"), "URWW")
        self.assertEqual(NoaaWeatherProvider.normalize_icao_code("usrr"), "USRR")


class OpenMeteoProviderTestCase(TestCase):
    """Тесты провайдера Open-Meteo (ECMWF IFS / GFS)."""

    def test_wmo_code_description(self):
        """Тест декодирования числовых WMO 4677 кодов."""
        self.assertEqual(WMO_WEATHER_CODES.get(0), "Ясно")
        self.assertEqual(WMO_WEATHER_CODES.get(61), "Слабый дождь")
        self.assertEqual(WMO_WEATHER_CODES.get(75), "Сильный снегопад")
        self.assertEqual(WMO_WEATHER_CODES.get(95), "Гроза (слабая или умеренная)")

    def test_parse_single_point_hourly(self):
        """Тест разбора почасового ответа Open-Meteo API."""
        mock_hourly = {
            "time": ["2026-09-19T06:00", "2026-09-19T07:00"],
            "temperature_2m": [12.5, 14.0],
            "dew_point_2m": [6.0, 7.0],
            "relative_humidity_2m": [65, 60],
            "precipitation": [0.0, 0.5],
            "weather_code": [0, 61],
            "pressure_msl": [1015.0, 1014.0],
            "surface_pressure": [1006.0, 1005.0],
            "cloud_cover": [25, 75],
            "cloud_cover_low": [10, 50],
            "cloud_cover_mid": [0, 20],
            "cloud_cover_high": [0, 10],
            "cloud_base": [1200, 800],
            "visibility": [10000.0, 6000.0],
            "wind_speed_10m": [4.5, 6.0],
            "wind_direction_10m": [220, 240],
            "wind_gusts_10m": [7.0, 10.0],
            "freezing_level_height": [2100.0, 2050.0],
        }
        records = OpenMeteoProvider.parse_single_point_hourly(mock_hourly)
        self.assertEqual(len(records), 2)
        p1 = records[0]
        self.assertEqual(p1["temperature"], 12.5)
        self.assertEqual(p1["model_flight_category"], "VFR")
        self.assertEqual(p1["pressure_msl_hpa"], 1015.0)
        self.assertAlmostEqual(p1["pressure_mmhg"], 761.3, places=1)


class WeatherManagerServiceTestCase(TestCase):
    """Тесты единого фасада WeatherManagerService."""

    def setUp(self):
        self.station = AviationWeatherStation.objects.create(
            icao_code="USRR",
            name="Surgut",
            name_ru="Сургут",
            latitude=61.3439,
            longitude=73.4025,
            elevation_msl_m=61.0,
        )
        self.mpd = PlaceProductionActivity.objects.create(
            name="МПД Нефтеюганск",
            short_name="Нефтеюганск",
            latitude=61.09,
            longitude=72.60,
            elevation_msl_m=45.0,
            elevation_source="MANUAL",
            weather_source_preference="AUTO",
            weather_monitoring_enabled=True,
        )

    def test_bundle_with_coordinate_forecast(self):
        """Тест формирования DTO бандла с сеточным прогнозом."""
        now = timezone.now()
        CoordinateWeatherForecast.objects.create(
            mpd=self.mpd,
            latitude=self.mpd.latitude,
            longitude=self.mpd.longitude,
            elevation_msl_m=self.mpd.elevation_msl_m,
            nearest_station=self.station,
            forecast_for=now,
            model_run_at=now,
            model="ecmwf_ifs",
            weather_code=0,
            temperature=15.0,
            dew_point=5.0,
            relative_humidity=50,
            wind_speed=4.0,
            wind_direction=180,
            visibility_m=10000,
            cloud_base_agl_m=1200,
            model_flight_category="VFR",
            freezing_level_msl_m=2500,
            surface_pressure_hpa=1008.0,
            surface_pressure_mmhg=756.1,
            pressure_msl_hpa=1013.25,
            pressure_mmhg=760.0,
        )

        bundle = WeatherManagerService.build_mpd_weather_bundle(self.mpd, now.date())
        self.assertEqual(bundle["source_type"], "COORDINATE_MODEL")
        self.assertFalse(bundle["is_observation"])
        self.assertIsNotNone(bundle["nearest_station_info"])
        self.assertIn(bundle["nearest_station_info"]["station"].icao_code, ("USRN", "USRR"))
        self.assertEqual(len(bundle["hourly_timeline"]), 1)


class WeatherViewsTestCase(TestCase):
    """Тесты HTTP представлений метеоцентра МПД."""

    def setUp(self):
        self.user = DataBaseUser.objects.create_user(
            username="test_weather_viewer",
            first_name="Петр",
            last_name="Петров",
            email="viewer@barkol.ru",
            password="testpassword123",
            title="Инженер МТО",
        )
        self.mpd = PlaceProductionActivity.objects.create(
            name="МПД Сургут",
            short_name="Сургут",
            icao_code="USRR",
            latitude=61.3439,
            longitude=73.4025,
            elevation_msl_m=61.0,
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

    def test_mpd_weather_refresh_coordinate_mode(self):
        """Тест эндпоинта обновления численного прогноза по координатам."""
        url = reverse("flight_planning:mpd_weather_refresh", args=[self.mpd.pk]) + "?mode=coordinate"
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("mode"), "coordinate")

    def test_mpd_weather_modal_view_coordinate_only(self):
        """Тест быстрого модального информера для посадочной площадки без ICAO с ECMWF прогнозом."""
        coord_mpd = PlaceProductionActivity.objects.create(
            name="Вертодром Приобское",
            short_name="Приобское",
            icao_code="",
            latitude=61.12,
            longitude=70.35,
            elevation_msl_m=35.0,
            in_planning=True,
            weather_monitoring_enabled=True,
        )
        now = timezone.now()
        CoordinateWeatherForecast.objects.create(
            mpd=coord_mpd,
            latitude=61.12,
            longitude=70.35,
            elevation_msl_m=35.0,
            forecast_for=now,
            model_run_at=now,
            model="ecmwf_ifs",
            weather_code=1,
            temperature=18.0,
            dew_point=7.0,
            relative_humidity=52,
            wind_speed=3.5,
            wind_direction=200,
            visibility_m=10000,
            cloud_base_agl_m=1500,
            model_flight_category="VFR",
            freezing_level_msl_m=2800,
            surface_pressure_hpa=1010.0,
            surface_pressure_mmhg=757.6,
            pressure_msl_hpa=1014.2,
            pressure_mmhg=760.7,
        )

        url = reverse("flight_planning:mpd_weather_modal", args=[coord_mpd.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вертодром Приобское")
        self.assertContains(response, "quickWeatherModalChart")
        self.assertContains(response, "ECMWF")

    def test_mpd_weather_history_view_coordinate_chart(self):
        """Тест отображения суточных графиков ECMWF на странице Метеоцентра для координатной площадки."""
        coord_mpd = PlaceProductionActivity.objects.create(
            name="Вертодром Салым",
            short_name="Салым",
            icao_code="",
            latitude=60.03,
            longitude=71.48,
            elevation_msl_m=50.0,
            in_planning=True,
            weather_monitoring_enabled=True,
        )
        now = timezone.now()
        CoordinateWeatherForecast.objects.create(
            mpd=coord_mpd,
            latitude=60.03,
            longitude=71.48,
            elevation_msl_m=50.0,
            forecast_for=now,
            model_run_at=now,
            model="ecmwf_ifs",
            weather_code=0,
            temperature=20.0,
            dew_point=8.0,
            relative_humidity=45,
            wind_speed=4.0,
            wind_direction=170,
            visibility_m=10000,
            cloud_base_agl_m=2000,
            model_flight_category="VFR",
            freezing_level_msl_m=3000,
            surface_pressure_hpa=1009.0,
            surface_pressure_mmhg=756.8,
            pressure_msl_hpa=1015.0,
            pressure_mmhg=761.3,
        )

        url = reverse("flight_planning:mpd_weather_history", args=[coord_mpd.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dailyWeatherChartEcmwf")
        self.assertContains(response, "dailyWeatherChartLarge")

    @patch("flight_planning.weather_services.AviationWeatherService.fetch_noaa_raw")
    @patch("flight_planning.weather_providers.open_meteo_provider.OpenMeteoProvider.fetch_coordinate_forecasts_batch")
    def test_sync_mpd_weather_with_progress_coordinate_point(self, mock_om, mock_noaa):
        """Тест пошаговой синхронизации метеоданных с протоколированием логов для координатной точки."""
        mock_noaa.return_value = {}
        now = timezone.now()

        coord_mpd = PlaceProductionActivity.objects.create(
            name="МПД Саратов Гагаринский",
            short_name="Саратов",
            icao_code="",
            latitude=51.648399,
            longitude=46.058534,
            elevation_msl_m=152.0,
            in_planning=True,
            weather_monitoring_enabled=True,
        )

        mock_om.return_value = [{
            "point": {"mpd_id": coord_mpd.pk, "latitude": 51.6484, "longitude": 46.0585},
            "model_name": "ecmwf_ifs",
            "elevation_msl_m": 150.0,
            "hourly_records": [
                {
                    "forecast_for": now,
                    "model_run_at": now,
                    "weather_code": 0,
                    "temperature": 22.0,
                    "dew_point": 9.0,
                    "relative_humidity": 45,
                    "surface_pressure_hpa": 1012.0,
                    "surface_pressure_mmhg": 759.1,
                    "pressure_msl_hpa": 1015.0,
                    "pressure_mmhg": 761.3,
                    "wind_speed": 4.5,
                    "wind_direction": 150,
                    "wind_gust": 7.0,
                    "cloud_cover_total": 10,
                    "cloud_cover_low": 5,
                    "cloud_cover_mid": 0,
                    "cloud_cover_high": 0,
                    "cloud_base_agl_m": 1800,
                    "freezing_level_msl_m": 2900,
                    "precipitation_mm": 0.0,
                    "precipitation_probability": 0,
                    "visibility_m": 10000,
                    "model_flight_category": "VFR",
                }
            ],
        }]

        res = AviationWeatherService.sync_mpd_weather_with_progress(coord_mpd, mode="all")
        self.assertTrue(res["success"])
        self.assertGreater(len(res["logs"]), 5)
        log_levels = [l["level"] for l in res["logs"]]
        self.assertIn("start", log_levels)
        self.assertIn("step", log_levels)
        self.assertIn("success", log_levels)
        self.assertEqual(res["stats"]["coordinate_points_saved"], 1)

    def test_mpd_weather_sync_run_view_endpoint(self):
        """Тест AJAX-эндпоинта запуска синхронизации погоды."""
        coord_mpd = PlaceProductionActivity.objects.create(
            name="МПД Тест Запуск",
            latitude=55.0,
            longitude=37.0,
            in_planning=True,
            weather_monitoring_enabled=True,
        )
        url = reverse("flight_planning:mpd_weather_sync_run", args=[coord_mpd.pk])
        response = self.client.post(
            url,
            {"mode": "coordinate"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            SERVER_NAME="localhost",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("success", data)
        self.assertIn("is_async", data)
        self.assertIn("task_name", data)

    def test_mpd_weather_sync_status_view_endpoint(self):
        """Тест AJAX-эндпоинта мониторинга статуса задачи."""
        coord_mpd = PlaceProductionActivity.objects.create(
            name="МПД Тест Статус",
            latitude=55.0,
            longitude=37.0,
            in_planning=True,
        )
        url = reverse("flight_planning:mpd_weather_sync_status", args=[coord_mpd.pk, "fake-task-id-12345"])
        response = self.client.get(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            SERVER_NAME="localhost",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("state", data)
        self.assertIn("ready", data)

    def test_get_mpd_current_weather_selects_closest_to_now(self):
        """Тест выбора актуального среза погоды, максимально близкого к текущему моменту (now)."""
        from flight_planning.weather_services import AviationWeatherService

        coord_mpd = PlaceProductionActivity.objects.create(
            name="МПД Тест Временная Зона",
            latitude=57.58,
            longitude=37.21,
            elevation_msl_m=182.0,
            in_planning=True,
            weather_monitoring_enabled=True,
        )
        now = timezone.now()

        # Создаем 3 точки: 6 часов назад, текущий час, и 11 часов вперед (ночь)
        past_forecast = CoordinateWeatherForecast.objects.create(
            mpd=coord_mpd,
            latitude=57.58,
            longitude=37.21,
            elevation_msl_m=182.0,
            forecast_for=now - timedelta(hours=6),
            model_run_at=now - timedelta(hours=12),
            model="ecmwf_ifs",
            temperature=12.0,
        )
        current_forecast = CoordinateWeatherForecast.objects.create(
            mpd=coord_mpd,
            latitude=57.58,
            longitude=37.21,
            elevation_msl_m=182.0,
            forecast_for=now,
            model_run_at=now - timedelta(hours=6),
            model="ecmwf_ifs",
            temperature=19.0,
        )
        night_forecast = CoordinateWeatherForecast.objects.create(
            mpd=coord_mpd,
            latitude=57.58,
            longitude=37.21,
            elevation_msl_m=182.0,
            forecast_for=now + timedelta(hours=11),
            model_run_at=now - timedelta(hours=6),
            model="ecmwf_ifs",
            temperature=9.0,
        )

        weather = AviationWeatherService.get_mpd_current_weather(coord_mpd)
        latest_coord = weather.get("latest_coordinate_forecast")

        self.assertIsNotNone(latest_coord)
        # Должен быть выбран срез на текущий момент (температура 19.0), а не ночной (9.0)
        self.assertEqual(latest_coord.pk, current_forecast.pk)
        self.assertEqual(latest_coord.temperature, 19.0)



