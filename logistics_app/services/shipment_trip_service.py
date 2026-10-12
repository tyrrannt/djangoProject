"""Сервисный слой управления рейсами и маршрутами доставки на МПД."""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union

from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser
from hrdepartment_app.models import PlaceProductionActivity
from logistics_app.models import Package, PackageEventLog, ShipmentTrip, TripStop

logger = logging.getLogger(__name__)


class ShipmentTripService:
    """Сервис управления рейсами автотранспорта и доставкой на МПД."""

    @classmethod
    def create_trip(
        cls,
        dispatcher: DataBaseUser,
        planned_date: date,
        origin_point: Optional[PlaceProductionActivity] = None,
        origin_custom: str = "Центральный склад (Москва)",
        destinations: Optional[List[PlaceProductionActivity]] = None,
        vehicle_type: str = ShipmentTrip.VehicleType.COMPANY_CAR,
        vehicle_model: str = "",
        vehicle_reg_number: str = "",
        driver_user: Optional[DataBaseUser] = None,
        driver_name: str = "",
        driver_phone: str = "",
        comment: str = "",
    ) -> ShipmentTrip:
        """Создает новый рейс машины с плановым маршрутом по точкам МПД.

        Args:
            dispatcher (DataBaseUser): Логист/диспетчер, формирующий рейс.
            planned_date (date): Планируемая дата отправления.
            origin_point (Optional[PlaceProductionActivity]): Точка отправления (МПД/база).
            origin_custom (str): Текстовое наименование пункта отправления. Defaults to "Центральный склад (Москва)".
            destinations (Optional[List[PlaceProductionActivity]]): Список МПД по маршруту следования.
            vehicle_type (str): Тип транспортного средства. Defaults to COMPANY_CAR.
            vehicle_model (str): Марка/модель автомобиля. Defaults to "".
            vehicle_reg_number (str): Государственный регистрационный номер ТС. Defaults to "".
            driver_user (Optional[DataBaseUser]): Назначенный водитель (сотрудник).
            driver_name (str): ФИО водителя / экспедитора. Defaults to "".
            driver_phone (str): Телефон водителя. Defaults to "".
            comment (str): Маршрутные указания и комментарии. Defaults to "".

        Returns:
            ShipmentTrip: Созданный экземпляр рейса с инициализированными остановками.
        """
        with transaction.atomic():
            trip = ShipmentTrip.objects.create(
                dispatcher=dispatcher,
                planned_date=planned_date,
                origin_point=origin_point,
                origin_custom=origin_custom,
                vehicle_type=vehicle_type,
                vehicle_model=vehicle_model.strip(),
                vehicle_reg_number=vehicle_reg_number.strip().upper(),
                driver_user=driver_user,
                driver_name=driver_name.strip(),
                driver_phone=driver_phone.strip(),
                comment=comment.strip(),
                status=ShipmentTrip.Status.PLANNING,
            )

            if destinations:
                for order, mpd in enumerate(destinations, start=1):
                    TripStop.objects.create(
                        trip=trip,
                        mpd=mpd,
                        stop_order=order,
                        planned_arrival_date=planned_date,
                        status=TripStop.Status.PENDING,
                    )

            logger.info("Сформирован рейс %s на дату %s (диспетчер: %s)", trip.trip_number, planned_date, dispatcher)
            return trip

    @classmethod
    def add_stop(
        cls,
        trip: ShipmentTrip,
        mpd: PlaceProductionActivity,
        stop_order: Optional[int] = None,
        planned_arrival_date: Optional[date] = None,
        comment: str = "",
    ) -> TripStop:
        """Добавляет остановку (заезд на МПД) в маршрут рейса.

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            mpd (PlaceProductionActivity): МПД назначения.
            stop_order (Optional[int]): Порядковый номер заезда. Если не указан, ставится в конец.
            planned_arrival_date (Optional[date]): Плановая дата прибытия на точку.
            comment (str): Примечание.

        Returns:
            TripStop: Созданная или обновленная остановка.
        """
        if stop_order is None:
            max_order = trip.stops.count()
            stop_order = max_order + 1

        stop, created = TripStop.objects.update_or_create(
            trip=trip,
            mpd=mpd,
            defaults={
                "stop_order": stop_order,
                "planned_arrival_date": planned_arrival_date or trip.planned_date,
                "comment": comment.strip(),
            },
        )
        return stop

    @classmethod
    def consolidate_trip(cls, trip: ShipmentTrip, user: DataBaseUser) -> ShipmentTrip:
        """Переводит рейс в статус скомплектованного (закрытие приема заявок, погрузка).

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            user (DataBaseUser): Сотрудник, фиксирующий комплектацию.

        Returns:
            ShipmentTrip: Обновленный рейс.

        Raises:
            ValueError: Если рейс не находится в статусе PLANNING.
        """
        if trip.status != ShipmentTrip.Status.PLANNING:
            raise ValueError(f"Рейс {trip.trip_number} находится в статусе {trip.get_status_display()} и не может быть скомплектован.")

        trip.status = ShipmentTrip.Status.CONSOLIDATED
        trip.save(update_fields=["status", "updated_at"])
        logger.info("Рейс %s скомплектован пользователем %s (посылок: %d)", trip.trip_number, user, trip.packages_count)
        return trip

    @classmethod
    def start_trip(cls, trip: ShipmentTrip, user: DataBaseUser) -> ShipmentTrip:
        """Запускает рейс (машина выехала со склада/базы).

        Автоматически переводит все прикрепленные посылки в статус IN_TRANSIT
        и регистрирует события в трекинг-журнале.

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            user (DataBaseUser): Диспетчер / логист, выпустивший машину.

        Returns:
            ShipmentTrip: Обновленный рейс.
        """
        now = timezone.now()
        with transaction.atomic():
            trip.status = ShipmentTrip.Status.IN_TRANSIT
            trip.actual_departure_at = now
            trip.save(update_fields=["status", "actual_departure_at", "updated_at"])

            vehicle_info = trip.vehicle_display
            driver_info = trip.driver_display

            # Обновляем все посылки в рейсе
            for pkg in trip.packages.all():
                pkg.status = Package.Status.IN_TRANSIT
                pkg.shipped_at = now
                pkg.save(update_fields=["status", "shipped_at", "updated_at"])

                PackageEventLog.objects.create(
                    package=pkg,
                    event_type=PackageEventLog.EventType.SHIPPED,
                    user=user,
                    timestamp=now,
                    message=f"Рейс {trip.trip_number} отправлен. Машина: {vehicle_info}, водитель: {driver_info}.",
                    location=trip.origin_display,
                )

            logger.info("Рейс %s отправлен в путь (посылок: %d)", trip.trip_number, trip.packages.count())
            return trip

    @classmethod
    def arrive_at_stop(
        cls,
        trip: ShipmentTrip,
        mpd: PlaceProductionActivity,
        user: DataBaseUser,
    ) -> TripStop:
        """Фиксирует прибытие машины на конкретный МПД.

        Переводит остановку в статус ARRIVED и переводит все посылки, адресованные
        на данный МПД, в статус DELIVERED_AT_MPD (ожидает приемки).

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            mpd (PlaceProductionActivity): МПД, на который прибыл транспорт.
            user (DataBaseUser): Сотрудник, зафиксировавший прибытие.

        Returns:
            TripStop: Обновленная точка маршрута.
        """
        now = timezone.now()
        with transaction.atomic():
            stop = TripStop.objects.filter(trip=trip, mpd=mpd).first()
            if stop:
                stop.status = TripStop.Status.ARRIVED
                stop.save(update_fields=["status"])

            # Посылки, направленные именно на этот МПД
            packages_for_mpd = trip.packages.filter(destination=mpd, status=Package.Status.IN_TRANSIT)
            for pkg in packages_for_mpd:
                pkg.status = Package.Status.DELIVERED_AT_MPD
                pkg.save(update_fields=["status", "updated_at"])

                PackageEventLog.objects.create(
                    package=pkg,
                    event_type=PackageEventLog.EventType.ARRIVED_AT_MPD,
                    user=user,
                    timestamp=now,
                    message=f"Машина рейса {trip.trip_number} прибыла на {mpd.name}. Груз ожидает приемки.",
                    location=mpd.name,
                )

            # Проверяем, не все ли точки пройдены
            all_stops_arrived = not trip.stops.filter(status=TripStop.Status.PENDING).exists()
            if all_stops_arrived and trip.status == ShipmentTrip.Status.IN_TRANSIT:
                trip.status = ShipmentTrip.Status.ARRIVED
                trip.save(update_fields=["status", "updated_at"])

            logger.info("Рейс %s прибыл на точку %s", trip.trip_number, mpd.name)
            return stop

    @classmethod
    def complete_trip(cls, trip: ShipmentTrip, user: DataBaseUser) -> ShipmentTrip:
        """Завершает рейс после разгрузки и приемки всех посылок по маршруту.

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            user (DataBaseUser): Сотрудник, закрывающий рейс.

        Returns:
            ShipmentTrip: Завершенный рейс.
        """
        now = timezone.now()
        with transaction.atomic():
            trip.status = ShipmentTrip.Status.COMPLETED
            trip.actual_completed_at = now
            trip.save(update_fields=["status", "actual_completed_at", "updated_at"])

            trip.stops.filter(status__in=[TripStop.Status.PENDING, TripStop.Status.ARRIVED]).update(
                status=TripStop.Status.DISCHARGED
            )

            logger.info("Рейс %s успешно завершен пользователем %s", trip.trip_number, user)
            return trip

    @classmethod
    def cancel_trip(cls, trip: ShipmentTrip, user: DataBaseUser, reason: str = "") -> ShipmentTrip:
        """Отменяет рейс и возвращает прикрепленные посылки в очередь ожидания.

        Args:
            trip (ShipmentTrip): Экземпляр рейса.
            user (DataBaseUser): Сотрудник, отменивший рейс.
            reason (str): Причина отмены.

        Returns:
            ShipmentTrip: Отмененный рейс.
        """
        now = timezone.now()
        with transaction.atomic():
            trip.status = ShipmentTrip.Status.CANCELLED
            if reason:
                trip.comment = f"{trip.comment}\n[ОТМЕНА]: {reason}".strip()
            trip.save(update_fields=["status", "comment", "updated_at"])

            # Возвращаем посылки в очередь
            for pkg in trip.packages.all():
                pkg.trip = None
                pkg.status = Package.Status.AWAITING_SHIPMENT
                pkg.save(update_fields=["trip", "status", "updated_at"])

                PackageEventLog.objects.create(
                    package=pkg,
                    event_type=PackageEventLog.EventType.REMOVED_FROM_TRIP,
                    user=user,
                    timestamp=now,
                    message=f"Рейс {trip.trip_number} отменен ({reason}). Посылка возвращена в очередь ожидания отправки.",
                    location=trip.origin_display,
                )

            logger.warning("Рейс %s отменен пользователем %s. Причина: %s", trip.trip_number, user, reason)
            return trip
