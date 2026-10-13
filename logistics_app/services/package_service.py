"""Сервисный слой управления посылками, описью вложения и приемкой на МПД."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity
from logistics_app.models import (
    Package,
    PackageEventLog,
    PackageImage,
    PackageItem,
    ShipmentTrip,
)

logger = logging.getLogger(__name__)


class PackageService:
    """Сервис управления жизненным циклом внутренних посылок и приемки на МПД."""

    @classmethod
    def create_package(
        cls,
        sender: DataBaseUser,
        destination: PlaceProductionActivity,
        origin: Optional[PlaceProductionActivity] = None,
        origin_custom: str = "Центральный склад (Москва)",
        sender_division: Optional[Division] = None,
        recipient: Optional[DataBaseUser] = None,
        trip: Optional[ShipmentTrip] = None,
        urgency: str = Package.Urgency.NORMAL,
        package_type: str = Package.PackageType.BOX,
        description: str = "",
        weight_kg: Optional[Decimal] = None,
        places_count: int = 1,
        items_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Package:
        """Создает карточку посылки с описью вложения.

        Если рейс указан, посылка сразу включается в него (ASSIGNED_TO_TRIP).
        Если рейс не указан, посылка ставится в пул ожидания (AWAITING_SHIPMENT).

        Args:
            sender (DataBaseUser): Отправитель посылки.
            destination (PlaceProductionActivity): МПД назначения.
            origin (Optional[PlaceProductionActivity]): МПД отправления (null для базы).
            origin_custom (str): Текстовый пункт отправления.
            sender_division (Optional[Division]): Подразделение отправителя.
            recipient (Optional[DataBaseUser]): Назначенный получатель на МПД.
            trip (Optional[ShipmentTrip]): Выбранный открытый рейс машины.
            urgency (str): Срочность доставки.
            package_type (str): Вид упаковки.
            description (str): Описание содержимого.
            weight_kg (Optional[Decimal]): Вес груза.
            places_count (int): Число физических мест.
            items_data (Optional[List[Dict[str, Any]]]): Список позиций описи вложения.

        Returns:
            Package: Созданный экземпляр посылки с заполненными позициями.
        """
        now = timezone.now()
        initial_status = Package.Status.ASSIGNED_TO_TRIP if trip else Package.Status.AWAITING_SHIPMENT

        # Автоматически определяем подразделение автора, если не передано явно
        if not sender_division:
            profile = getattr(sender, "user_work_profile", None)
            if profile and hasattr(profile, "divisions"):
                try:
                    divisions = profile.divisions.all()
                    if divisions.exists():
                        sender_division = divisions.first()
                except Exception:
                    pass

        with transaction.atomic():
            package = Package.objects.create(
                sender=sender,
                sender_division=sender_division,
                origin=origin,
                origin_custom=origin_custom,
                destination=destination,
                recipient=recipient,
                trip=trip,
                urgency=urgency,
                package_type=package_type,
                description=description.strip(),
                weight_kg=weight_kg,
                places_count=places_count,
                status=initial_status,
                created_at=now,
            )

            # Создаем позиции описи вложения
            if items_data:
                for idx, item_raw in enumerate(items_data, start=1):
                    name = str(item_raw.get("name", "")).strip()
                    if not name:
                        continue
                    PackageItem.objects.create(
                        package=package,
                        item_order=idx,
                        name=name,
                        part_number=str(item_raw.get("part_number", "")).strip(),
                        serial_number=str(item_raw.get("serial_number", "")).strip(),
                        quantity_sent=Decimal(str(item_raw.get("quantity_sent", 1))),
                        unit=str(item_raw.get("unit", "шт.")).strip() or "шт.",
                        sender_comment=str(item_raw.get("sender_comment", "")).strip(),
                        item_status=PackageItem.ItemStatus.PENDING,
                    )

            # Фиксируем создание в трекинг-журнале
            PackageEventLog.objects.create(
                package=package,
                event_type=PackageEventLog.EventType.CREATED,
                user=sender,
                timestamp=now,
                message=f"Посылка оформлена отправителем. Направление: {package.origin_display} → {package.destination_display}.",
                location=package.origin_display,
            )

            if trip:
                PackageEventLog.objects.create(
                    package=package,
                    event_type=PackageEventLog.EventType.ATTACHED_TO_TRIP,
                    user=sender,
                    timestamp=now,
                    message=f"Посылка включена в рейс {trip.trip_number} (выезд {trip.planned_date.strftime('%d.%m.%Y')}).",
                    location=package.origin_display,
                )

            logger.info("Создана посылка %s на МПД %s (отправитель: %s)", package.track_number, destination.name, sender)
            return package

    @classmethod
    def attach_to_trip(cls, package: Package, trip: ShipmentTrip, user: DataBaseUser) -> Package:
        """Прикрепляет готовую посылку к открытому рейсу автомобиля.

        Args:
            package (Package): Посылка из очереди.
            trip (ShipmentTrip): Рейс машины.
            user (DataBaseUser): Сотрудник, выполняющий назначение.

        Returns:
            Package: Обновленная посылка.

        Raises:
            ValueError: Если рейс отменен/завершен или посылка уже в пути.
        """
        if trip.status in [ShipmentTrip.Status.COMPLETED, ShipmentTrip.Status.CANCELLED]:
            raise ValueError(f"Невозможно привязать посылку к рейсу {trip.trip_number} со статусом {trip.get_status_display()}.")

        if package.status in [Package.Status.IN_TRANSIT, Package.Status.RECEIVED_FULL, Package.Status.RECEIVED_WITH_DISCREPANCY]:
            raise ValueError(f"Посылка {package.track_number} уже находится в статусе {package.get_status_display()}.")

        now = timezone.now()
        with transaction.atomic():
            package.trip = trip
            package.status = Package.Status.ASSIGNED_TO_TRIP
            package.save(update_fields=["trip", "status", "updated_at"])

            PackageEventLog.objects.create(
                package=package,
                event_type=PackageEventLog.EventType.ATTACHED_TO_TRIP,
                user=user,
                timestamp=now,
                message=f"Посылка включена в рейс {trip.trip_number} (выезд {trip.planned_date.strftime('%d.%m.%Y')}).",
                location=trip.origin_display,
            )

            logger.info("Посылка %s прикреплена к рейсу %s", package.track_number, trip.trip_number)
            return package

    @classmethod
    def detach_from_trip(cls, package: Package, user: DataBaseUser, reason: str = "") -> Package:
        """Исключает посылку из рейса и возвращает в очередь ожидания отправки.

        Args:
            package (Package): Посылка.
            user (DataBaseUser): Сотрудник, исключающий посылку.
            reason (str): Причина исключения.

        Returns:
            Package: Обновленная посылка.
        """
        now = timezone.now()
        old_trip_num = package.trip.trip_number if package.trip else "—"

        with transaction.atomic():
            package.trip = None
            package.status = Package.Status.AWAITING_SHIPMENT
            package.save(update_fields=["trip", "status", "updated_at"])

            msg = f"Посылка исключена из рейса {old_trip_num} и возвращена в очередь."
            if reason:
                msg += f" Причина: {reason}."

            PackageEventLog.objects.create(
                package=package,
                event_type=PackageEventLog.EventType.REMOVED_FROM_TRIP,
                user=user,
                timestamp=now,
                message=msg,
                location=package.origin_display,
            )

            logger.info("Посылка %s исключена из рейса %s", package.track_number, old_trip_num)
            return package

    @classmethod
    def receive_package_on_mpd(
        cls,
        package: Package,
        user: DataBaseUser,
        items_reception: List[Dict[str, Any]],
        photos: Optional[List[UploadedFile]] = None,
        reception_comment: str = "",
    ) -> Package:
        """Выполняет построчную приемочную сверку позиций посылки на МПД.

        Проверяет принятое количество, выявляет расхождения/недостачу/повреждения,
        сохраняет фотофиксацию, рассчитывает итоговый статус и фактическое время в пути.

        Args:
            package (Package): Принимаемая посылка.
            user (DataBaseUser): Ответственный сотрудник на МПД, принимающий груз.
            items_reception (List[Dict[str, Any]]): Данные сверки по каждой позиции
                (id, quantity_received, item_status, discrepancy_comment).
            photos (Optional[List[UploadedFile]]): Загруженные фотографии дефектов/приемки.
            reception_comment (str): Итоговое примечание или номер акта приемки.

        Returns:
            Package: Принятая посылка с обновленным статусом.
        """
        now = timezone.now()
        has_any_discrepancy = False

        with transaction.atomic():
            # 1. Построчная сверка позиций описи
            items_by_id = {item.id: item for item in package.items.all()}

            for rec_data in items_reception:
                item_id = rec_data.get("id")
                if not item_id or int(item_id) not in items_by_id:
                    continue

                item = items_by_id[int(item_id)]
                qty_rec = rec_data.get("quantity_received")

                if qty_rec is not None and str(qty_rec).strip() != "":
                    try:
                        item.quantity_received = Decimal(str(qty_rec))
                    except Exception:
                        item.quantity_received = item.quantity_sent
                else:
                    item.quantity_received = item.quantity_sent

                status = rec_data.get("item_status", PackageItem.ItemStatus.ACCEPTED)
                comment = str(rec_data.get("discrepancy_comment", "")).strip()

                # Автоматическая проверка на недостачу, если количество меньше отправленного
                if item.quantity_received < item.quantity_sent and status == PackageItem.ItemStatus.ACCEPTED:
                    status = PackageItem.ItemStatus.SHORTAGE

                if status in [PackageItem.ItemStatus.SHORTAGE, PackageItem.ItemStatus.DAMAGED] or item.quantity_received != item.quantity_sent:
                    has_any_discrepancy = True

                item.item_status = status
                item.discrepancy_comment = comment
                item.save(update_fields=["quantity_received", "item_status", "discrepancy_comment"])

                # Синхронизация жизненного цикла инструмента ТО (ФАП-145) при успешной приемке
                if (
                    item.maintenance_equipment
                    and status == PackageItem.ItemStatus.ACCEPTED
                    and package.destination
                ):
                    eq = item.maintenance_equipment
                    eq.production_place = package.destination
                    eq.save(update_fields=["production_place", "updated_at"])
                    logger.info(
                        "Местонахождение инструмента ТО %s (S/N %s) обновлено на МПД %s",
                        eq.name,
                        eq.serial_number,
                        package.destination.name,
                    )

            # 2. Сохранение прикрепленных фотографий приемки
            if photos:
                for photo_file in photos:
                    if photo_file:
                        PackageImage.objects.create(
                            package=package,
                            image=photo_file,
                            caption=f"Приемка на МПД ({user.title or user.username})",
                            stage=PackageImage.Stage.RECEPTION,
                            uploaded_by=user,
                            created_at=now,
                        )

            # 3. Фиксация общего статуса посылки
            final_status = (
                Package.Status.RECEIVED_WITH_DISCREPANCY
                if has_any_discrepancy
                else Package.Status.RECEIVED_FULL
            )

            package.status = final_status
            package.has_discrepancy = has_any_discrepancy
            package.received_at = now
            package.received_by = user
            package.reception_comment = reception_comment.strip()
            package.save(update_fields=[
                "status",
                "has_discrepancy",
                "received_at",
                "received_by",
                "reception_comment",
                "updated_at",
            ])

            # 4. Регистрация в журнале трекинга
            event_type = (
                PackageEventLog.EventType.RECEIVED_DISCREPANCY
                if has_any_discrepancy
                else PackageEventLog.EventType.RECEIVED_FULL
            )
            discrepancy_text = " (зафиксированы расхождения/недостача)" if has_any_discrepancy else " (все позиции приняты в полном объеме)"
            PackageEventLog.objects.create(
                package=package,
                event_type=event_type,
                user=user,
                timestamp=now,
                message=f"Груз принят на {package.destination_display} сотрудником {user.title or user.get_full_name() or user.username}{discrepancy_text}.",
                location=package.destination_display,
            )

            logger.info("Посылка %s принята на МПД %s со статусом %s (принял: %s)", package.track_number, package.destination_display, final_status, user)
            return package

    @classmethod
    def add_photo(
        cls,
        package: Package,
        image_file: UploadedFile,
        user: DataBaseUser,
        stage: str = PackageImage.Stage.SHIPMENT,
        caption: str = "",
        item: Optional[PackageItem] = None,
    ) -> PackageImage:
        """Добавляет фотографию груза или конкретной позиции к посылке.

        Args:
            package (Package): Посылка.
            image_file (UploadedFile): Файл фото.
            user (DataBaseUser): Загрузивший сотрудник.
            stage (str): Этап съемки (SHIPMENT или RECEPTION).
            caption (str): Подпись к фотографии.
            item (Optional[PackageItem]): Конкретная позиция при наличии.

        Returns:
            PackageImage: Созданный объект фотографии.
        """
        now = timezone.now()
        photo = PackageImage.objects.create(
            package=package,
            image=image_file,
            caption=caption.strip(),
            stage=stage,
            item=item,
            uploaded_by=user,
            created_at=now,
        )

        PackageEventLog.objects.create(
            package=package,
            event_type=PackageEventLog.EventType.PHOTO_ADDED,
            user=user,
            timestamp=now,
            message=f"Добавлена фотография ({photo.get_stage_display()}): {caption or 'без описания'}.",
            location=package.destination_display if stage == PackageImage.Stage.RECEPTION else package.origin_display,
        )
        return photo
