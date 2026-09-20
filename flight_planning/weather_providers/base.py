"""Абстрактный базовый интерфейс поставщиков метеорологических данных."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseWeatherProvider(ABC):
    """Абстрактный класс поставщика метеорологических данных (METAR, TAF, NWP).

    Определяет общий контракт для провайдеров авиационной метеорологии (NOAA AWC,
    Open-Meteo, ECMWF, GFS, ICON и др.).
    """

    @abstractmethod
    def fetch_current(self, *args: Any, **kwargs: Any) -> Any:
        """Получает текущие фактические метеонаблюдения или ближайший срез погоды.

        Args:
            *args (Any): Позиционные аргументы запроса.
            **kwargs (Any): Именованные аргументы запроса.

        Returns:
            Any: Структура данных фактической погоды.
        """
        pass

    @abstractmethod
    def fetch_forecast(self, *args: Any, **kwargs: Any) -> Any:
        """Получает прогноз погоды (аэродромный TAF или сеточный численный прогноз).

        Args:
            *args (Any): Позиционные аргументы запроса.
            **kwargs (Any): Именованные аргументы запроса.

        Returns:
            Any: Структура данных прогноза погоды.
        """
        pass
