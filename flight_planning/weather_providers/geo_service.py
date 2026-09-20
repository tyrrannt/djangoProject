"""Геодезический сервис расчета расстояний и поиска опорных метеостанций."""

import math
from typing import Any, Dict, List, Optional, Tuple

from flight_planning.models import AviationWeatherStation, PlaceProductionActivity


class GeoStationService:
    """Сервис гео-пространственных вычислений и подбора опорных аэродромов.

    Использует сферическую тригонометрию (формулу Haversine) для нахождения
    ближайших сертифицированных метеостанций (АМСГ/ICAO) и вычисляет перепад
    высот над средним уровнем моря (MSL).
    """

    EARTH_RADIUS_KM: float = 6371.0
    MAX_REPRESENTATIVE_DISTANCE_KM: float = 15.0

    @classmethod
    def haversine_distance(
        cls,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Вычисляет ортодромическое расстояние между двумя координатами по формуле Haversine.

        Args:
            lat1 (float): Широта первой точки в градусах.
            lon1 (float): Долгота первой точки в градусах.
            lat2 (float): Широта второй точки в градусах.
            lon2 (float): Долгота второй точки в градусах.

        Returns:
            float: Расстояние между точками в километрах (с округлением до 1 знака).
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        distance = cls.EARTH_RADIUS_KM * c
        return round(distance, 1)

    @classmethod
    def calculate_elevation_delta(
        cls,
        mpd_elevation_msl_m: Optional[float],
        station_elevation_msl_m: Optional[float],
    ) -> Optional[float]:
        """Вычисляет разницу высот между площадкой МПД и контрольной точкой метеостанции.

        Положительное значение означает, что площадка находится выше метеостанции,
        отрицательное — ниже.

        Args:
            mpd_elevation_msl_m (Optional[float]): Высота площадки над уровнем моря (MSL, м).
            station_elevation_msl_m (Optional[float]): Высота метеостанции над уровнем моря (MSL, м).

        Returns:
            Optional[float]: Перепад высот в метрах (ΔH = H_мпд - H_станции) или None.
        """
        if mpd_elevation_msl_m is None or station_elevation_msl_m is None:
            return None
        return round(mpd_elevation_msl_m - station_elevation_msl_m, 1)

    @classmethod
    def find_nearest_station(
        cls,
        latitude: float,
        longitude: float,
        mpd_elevation_msl_m: Optional[float] = None,
        max_distance_km: float = 600.0,
    ) -> Optional[Dict[str, Any]]:
        """Находит ближайшую активную метеостанцию из справочника AviationWeatherStation.

        Определяет ортодромическое расстояние, перепад высот и проверяет критерий
        репрезентативности (расстояние не более 15 км от площадки).

        Args:
            latitude (float): Широта целевой точки в градусах.
            longitude (float): Долгота целевой точки в градусах.
            mpd_elevation_msl_m (Optional[float]): Высота точки (MSL, м) для расчета ΔH.
            max_distance_km (float): Максимальный радиус поиска в км (по умолчанию 600 км).

        Returns:
            Optional[Dict[str, Any]]: Словарь с информацией о ближайшей станции:
                - 'station': Объект модели AviationWeatherStation.
                - 'distance_km': Расстояние в км.
                - 'elevation_delta_m': Перепад высот в метрах (или None).
                - 'is_representative': True, если расстояние <= 15 км.
                - 'is_distant': True, если расстояние > 15 км (данные METAR сугубо справочные).
                - 'max_representative_km': Пороговая граница (15.0 км).
        """
        active_stations = AviationWeatherStation.objects.filter(is_active=True)
        if not active_stations.exists():
            return None

        best_station: Optional[AviationWeatherStation] = None
        min_distance: float = float("inf")

        for station in active_stations:
            dist = cls.haversine_distance(latitude, longitude, station.latitude, station.longitude)
            if dist < min_distance:
                min_distance = dist
                best_station = station

        if best_station is None or min_distance > max_distance_km:
            return None

        elevation_delta = cls.calculate_elevation_delta(
            mpd_elevation_msl_m,
            best_station.elevation_msl_m,
        )

        is_representative = min_distance <= cls.MAX_REPRESENTATIVE_DISTANCE_KM

        return {
            "station": best_station,
            "distance_km": min_distance,
            "elevation_delta_m": elevation_delta,
            "is_representative": is_representative,
            "is_distant": not is_representative,
            "max_representative_km": cls.MAX_REPRESENTATIVE_DISTANCE_KM,
        }
