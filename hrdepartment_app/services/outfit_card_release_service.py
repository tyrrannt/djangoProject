"""Сервисный слой валидации, метрологического контроля и закрытия карты-наряда ТО ВС (ФАП-145).

Данный модуль реализует требования Федеральных авиационных правил
(Приказ Минтранса РФ от 18.10.2024 № 367, Разделы III, IV, V и XV) и Федерального закона
от 26.06.2008 № 102-ФЗ «Об обеспечении единства измерений»:
- Метрологический учет и контроль пригодности средств измерений, КПА и специнструмента (пп. 19–25);
- Блокировка применения неисправного оборудования и инструмента из изолятора брака (пп. 24, 25);
- Фиксация неизменяемых снимков (snapshots) состояния метрологии приборов на дату выполнения ТО;
- Транзакционная проверка готовности карты-наряда к выпуску Свидетельства о ТО ВС (CRS);
- Формирование криптографического хэша неизменяемости (SHA-256) по п. 40 ФАП-145.
"""

import hashlib
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from customers_app.models import DataBaseUser
from hrdepartment_app.models import (
    ComponentOperationType,
    EquipmentOperationalStatus,
    EquipmentVerificationType,
    MaintenanceEquipment,
    MaintenanceReleaseCertificate,
    OutfitCard,
    OutfitCardEquipmentUsage,
)

logger = logging.getLogger(__name__)


def attach_equipment_to_outfit_card(
    outfit_card: OutfitCard,
    equipment: MaintenanceEquipment,
    user: Optional[DataBaseUser] = None,
    notes: str = "",
) -> OutfitCardEquipmentUsage:
    """Прикрепляет единицу оборудования/инструмента к карте-наряду с фиксацией неизменяемого снимка.

    Выполняет проверку применимости инструмента к типу воздушного судна,
    оценку физического состояния и срока поверки на дату проведения работ.

    Args:
        outfit_card (OutfitCard): Карта-наряд на выполнение ТО ВС.
        equipment (MaintenanceEquipment): Добавляемое оборудование из реестра.
        user (Optional[DataBaseUser]): Специалист, привязавший инструмент.
        notes (str): Примечание или технологический этап использования.

    Returns:
        OutfitCardEquipmentUsage: Созданная или обновленная запись использования со снимком.

    Raises:
        ValidationError: Если наряд уже закрыт или инструмент не применим к типу ВС.
    """
    if outfit_card.is_signed:
        raise ValidationError(
            f"Карта-наряд №{outfit_card.outfit_card_number} уже подписана (CRS). "
            "Изменение состава использованного инструмента и оборудования запрещено (п. 40 ФАП-145)."
        )

    # Проверка применимости к типу обслуживаемого ВС
    air_board = outfit_card.air_board
    if (
        air_board
        and air_board.type_property
        and equipment.applicable_aircraft_types.exists()
    ):
        if not equipment.applicable_aircraft_types.filter(pk=air_board.type_property.pk).exists():
            aircraft_name = str(air_board.type_property)
            raise ValidationError(
                f"Инструмент '{equipment.name}' (P/N: {equipment.part_number or '—'}) "
                f"не применим к типу ВС '{aircraft_name}' согласно реестру оборудования ТО."
            )

    target_date = (
        outfit_card.outfit_card_date_end
        or outfit_card.outfit_card_date
        or timezone.now().date()
    )

    is_valid, reason = equipment.can_be_used_for_maintenance(target_date)

    usage, _ = OutfitCardEquipmentUsage.objects.update_or_create(
        outfit_card=outfit_card,
        equipment=equipment,
        defaults={
            "equipment_name": equipment.name,
            "part_number": equipment.part_number,
            "serial_number": equipment.serial_number,
            "inventory_number": equipment.inventory_number,
            "marking_code": equipment.marking_code,
            "equipment_type": equipment.equipment_type,
            "verification_type": equipment.verification_type,
            "last_verification_date": equipment.last_verification_date,
            "next_verification_date": equipment.next_verification_date,
            "arshin_number": equipment.arshin_verification_number,
            "is_valid_at_usage": is_valid,
            "validation_message": reason,
            "attached_by": user,
            "notes": notes,
        },
    )

    logger.info(
        "Equipment %s attached to outfit card %s (valid: %s, reason: %s)",
        equipment.pk,
        outfit_card.pk,
        is_valid,
        reason,
    )
    return usage


def detach_equipment_from_outfit_card(outfit_card: OutfitCard, equipment_usage_id: int) -> bool:
    """Удаляет привязку оборудования из незакрытой карты-наряда.

    Args:
        outfit_card (OutfitCard): Карта-наряд ТО.
        equipment_usage_id (int): Идентификатор записи OutfitCardEquipmentUsage.

    Returns:
        bool: True при успешном удалении.

    Raises:
        ValidationError: Если наряд уже закрыт и подписан.
    """
    if outfit_card.is_signed:
        raise ValidationError(
            f"Карта-наряд №{outfit_card.outfit_card_number} уже подписана. "
            "Удаление оборудования запрещено."
        )

    deleted_count, _ = OutfitCardEquipmentUsage.objects.filter(
        pk=equipment_usage_id,
        outfit_card=outfit_card,
    ).delete()
    return deleted_count > 0


def get_staff_fap145_qualification_status(
    staff: DataBaseUser,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Определяет статус аттестации специалиста подтверждающего персонала по ФАП-145 (testing_app).

    По внутреннему регламенту организации ТО на основании требований ФАП-145 (п. 84)
    успешное прохождение периодического экзаменационного тестирования продлевает допуск
    к выпуску ВС на 6 месяцев от даты сдачи теста.

    Args:
        staff (DataBaseUser): Проверяемый специалист.
        target_date (Optional[date]): Контрольная дата проверки (по умолчанию текущая дата).

    Returns:
        Dict[str, Any]: Словарь с реквизитами допуска:
            - 'has_passed_exam' (bool): Факт успешной сдачи;
            - 'passed_at' (Optional[date]): Дата успешного тестирования;
            - 'valid_until' (Optional[date]): Срок окончания допуска (+6 месяцев);
            - 'status' (str): Код статуса ('VALID', 'EXPIRING', 'EXPIRED', 'NOT_PASSED');
            - 'is_valid' (bool): Признак действующего допуска на заданную дату;
            - 'testing_title' (str): Наименование пройденного тестирования;
            - 'score' (float): Лучший набранный балл в процентах;
            - 'badge_html' (str): HTML-бейдж для отображения в интерфейсе наряда.
    """
    from dateutil.relativedelta import relativedelta
    from testing_app.models import TestingAssignment

    check_date = target_date or timezone.now().date()

    # Поиск успешных прохождений тестирования
    passed_assignments = (
        TestingAssignment.objects.filter(
            employee=staff,
            status=TestingAssignment.Status.PASSED,
            passed_at__isnull=False,
        )
        .select_related("testing")
        .order_by("-passed_at")
    )

    # Приоритетно ищем тестирование по ФАП-145 или квалификации ТО ВС
    fap_assignment = None
    for assignment in passed_assignments:
        title_lower = assignment.testing.title.lower()
        if "фап-145" in title_lower or "то вс" in title_lower or "подтверждающ" in title_lower:
            fap_assignment = assignment
            break

    # Если специализированного нет, берем самое свежее успешное
    latest_assignment = fap_assignment or passed_assignments.first()

    if not latest_assignment or not latest_assignment.passed_at:
        return {
            "has_passed_exam": False,
            "passed_at": None,
            "valid_until": None,
            "status": "NOT_PASSED",
            "is_valid": False,
            "testing_title": "",
            "score": 0.0,
            "badge_html": '<span class="badge bg-secondary text-white">Аттестация не сдавалась</span>',
        }

    exam_date = latest_assignment.passed_at.date()
    valid_until = exam_date + relativedelta(months=6)

    if valid_until >= check_date:
        days_left = (valid_until - check_date).days
        if days_left <= 30:
            status = "EXPIRING"
            badge = f'<span class="badge bg-warning text-dark">Допуск истекает {valid_until:%d.%m.%Y} ({days_left} дн.)</span>'
        else:
            status = "VALID"
            badge = f'<span class="badge bg-success text-white">Аттестован по ФАП-145 до {valid_until:%d.%m.%Y}</span>'
        is_valid = True
    else:
        status = "EXPIRED"
        badge = f'<span class="badge bg-danger text-white">Допуск просрочен {valid_until:%d.%m.%Y}</span>'
        is_valid = False

    return {
        "has_passed_exam": True,
        "passed_at": exam_date,
        "valid_until": valid_until,
        "status": status,
        "is_valid": is_valid,
        "testing_title": latest_assignment.testing.title,
        "score": latest_assignment.best_score or 0.0,
        "badge_html": badge,
    }


def validate_outfit_card_for_release(outfit_card: OutfitCard) -> Tuple[bool, List[str]]:
    """Выполняет комплексный аудит готовности карты-наряда к выпуску CRS по ФАП-145.

    Проверяет:
    1. Наличие воздушного судна и даты выполнения наряда;
    2. Полноту объема выполненных работ (регламентных или оперативных);
    3. Подтверждающий персонал, наличие свидетельства специалиста по ТО ВС,
       допуск к типу обслуживаемого ВС и действующую аттестацию (допуск на 6 месяцев);
    4. Легитимность установленных авиационных компонентов (входящие документы о годности
       по п. 28 ФАП-145 и действующие сертификаты ремонтных организаций по п. 96);
    5. Метрологическую пригодность всех использованных инструментов, средств измерений (102-ФЗ)
       и КПА на дату ТО (пп. 19–25 ФАП-145).

    Args:
        outfit_card (OutfitCard): Проверяемая карта-наряд.

    Returns:
        Tuple[bool, List[str]]: (готов_к_выпуску, список_выявленных_замечаний).
    """
    errors: List[str] = []

    # 1. Основные реквизиты наряда
    if not outfit_card.air_board:
        errors.append("Не указано обслуживаемое воздушное судно (борт ВС).")

    target_date = (
        outfit_card.outfit_card_date_end
        or outfit_card.outfit_card_date
        or timezone.now().date()
    )

    if not outfit_card.outfit_card_date:
        errors.append("Не указана дата открытия карты-наряда.")

    # 2. Выполненные работы
    has_works = (
        outfit_card.operational_work.exists()
        or outfit_card.periodic_work.exists()
        or bool(outfit_card.other_work.strip())
    )
    if not has_works:
        errors.append("Не указаны выполненные работы (оперативные, регламентные или другие работы).")

    # 3. Подтверждающий персонал (п. 84 ФАП-145)
    staff = outfit_card.certifying_staff
    if not staff:
        errors.append("Не назначен специалист подтверждающего персонала для выпуска ВС (CRS).")
    else:
        license_num = getattr(staff, "maintenance_staff_certificate", "")
        if not license_num or not license_num.strip():
            errors.append(
                f"У подтверждающего специалиста {staff.get_full_name()} отсутствует "
                "номер свидетельства специалиста по ТО ВС (п. 84 ФАП-145)."
            )

        # Проверка допуска к типу ВС
        air_board = outfit_card.air_board
        if (
            air_board
            and air_board.type_property
            and hasattr(staff, "allowed_aircraft_types")
            and staff.allowed_aircraft_types.exists()
        ):
            if not staff.allowed_aircraft_types.filter(pk=air_board.type_property.pk).exists():
                errors.append(
                    f"Подтверждающий специалист {staff.get_full_name()} не имеет допуска "
                    f"к типу ВС '{air_board.type_property}' по свидетельству специалиста."
                )

        # Проверка периодической аттестации (допуск на 6 месяцев)
        qual = get_staff_fap145_qualification_status(staff, target_date)
        if qual["has_passed_exam"] and not qual["is_valid"]:
            errors.append(
                f"Срок действия допуска подтверждающего специалиста {staff.get_full_name()} "
                f"по результатам аттестации ФАП-145 истек {qual['valid_until']:%d.%m.%Y} "
                "(допуск выдается на 6 месяцев). Требуется повторная аттестация."
            )

    # 4. Проверка установленных компонентов (пп. 28, 96 ФАП-145)
    for comp_op in outfit_card.component_operations.select_related("installed_component", "installed_component__last_repair_org").all():
        if comp_op.operation_type in (ComponentOperationType.INSTALL, ComponentOperationType.REPLACE):
            comp = comp_op.installed_component
            if not comp:
                errors.append(f"В операции '{comp_op.get_operation_type_display()}' не выбран устанавливаемый агрегат.")
                continue

            if not comp.release_doc_number.strip():
                errors.append(
                    f"Компонент '{comp.name}' (S/N {comp.serial_number}) не имеет входящего документа о годности "
                    "(Талон годности, паспорт или этикетка по п. 28 ФАП-145)."
                )

            if comp.last_repair_org:
                org = comp.last_repair_org
                if not org.is_certificate_valid(target_date):
                    errors.append(
                        f"Сертификат организации '{org.short_name}' (№ {org.certificate_number}) "
                        f"недействителен на дату ТО {target_date:%d.%m.%Y} (п. 96 ФАП-145)."
                    )

    # 5. Метрологический аудит оборудования и инструмента (пп. 19-25 ФАП-145, 102-ФЗ)
    usages = outfit_card.used_equipment_records.select_related("equipment").all()
    for usage in usages:
        eq = usage.equipment
        is_allowed, reason = eq.can_be_used_for_maintenance(target_date)
        if not is_allowed:
            errors.append(
                f"Инструмент/прибор '{eq.name}' (P/N: {eq.part_number or '—'}, S/N: {eq.serial_number or 'б/н'}): {reason}"
            )

    is_valid = len(errors) == 0
    return is_valid, errors


def get_outfit_card_equipment_summary(outfit_card: OutfitCard) -> Dict[str, Any]:
    """Формирует сводку метрологического обеспечения карты-наряда для UI и отчетов.

    Args:
        outfit_card (OutfitCard): Карта-наряд ТО.

    Returns:
        Dict[str, Any]: Словарь метрик и списков оборудования по категориям готовности.
    """
    target_date = (
        outfit_card.outfit_card_date_end
        or outfit_card.outfit_card_date
        or timezone.now().date()
    )

    usages = outfit_card.used_equipment_records.select_related("equipment").all()
    total_count = len(usages)
    valid_count = 0
    expiring_count = 0
    invalid_count = 0
    invalid_items: List[Dict[str, str]] = []

    for usage in usages:
        eq = usage.equipment
        is_allowed, reason = eq.can_be_used_for_maintenance(target_date)
        if is_allowed:
            valid_count += 1
            if eq.metrology_status == "EXPIRING":
                expiring_count += 1
        else:
            invalid_count += 1
            invalid_items.append({
                "name": eq.name,
                "serial_number": eq.serial_number or "—",
                "part_number": eq.part_number or "—",
                "reason": reason,
            })

    return {
        "total_count": total_count,
        "valid_count": valid_count,
        "expiring_count": expiring_count,
        "invalid_count": invalid_count,
        "invalid_items": invalid_items,
        "is_metrology_ready": invalid_count == 0,
        "target_date": target_date,
    }


def calculate_outfit_card_release_hash(outfit_card: OutfitCard) -> str:
    """Вычисляет криптографический хэш неизменяемости (SHA-256) по п. 40 ФАП-145.

    Хэш включает реквизиты борта, дату наряда, наработку планера, перечень работ,
    идентификаторы установленных агрегатов и контрольные суммы использованного
    метрологического оборудования.

    Args:
        outfit_card (OutfitCard): Карта-наряд ТО.

    Returns:
        str: 64-символьный хэш SHA-256.
    """
    comp_ids = sorted([
        f"{c.pk}:{c.installed_component_id}:{c.operation_type}"
        for c in outfit_card.component_operations.all()
    ])
    equipment_ids = sorted([
        f"{u.equipment_id}:{u.serial_number}:{u.next_verification_date}"
        for u in outfit_card.used_equipment_records.all()
    ])

    payload = (
        f"CARD:{outfit_card.pk}|NO:{outfit_card.outfit_card_number}|DATE:{outfit_card.outfit_card_date}|"
        f"AIR:{outfit_card.air_board_id}|HOURS:{outfit_card.flight_hours}|CYCLES:{outfit_card.flight_cycles}|"
        f"STAFF:{outfit_card.certifying_staff_id}|COMPS:{','.join(comp_ids)}|EQ:{','.join(equipment_ids)}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@transaction.atomic
def release_and_sign_outfit_card(
    outfit_card: OutfitCard,
    certifying_staff: DataBaseUser,
    user_ip: str = "",
) -> MaintenanceReleaseCertificate:
    """Транзакционно закрывает карту-наряд, фиксирует хэш неизменяемости и выпускает CRS.

    Выполняет блокировку строки карты-наряда (select_for_update), комплексную валидацию
    всех требований ФАП-145, установку флагов закрытия и генерацию Свидетельства о ТО ВС (CRS).

    Args:
        outfit_card (OutfitCard): Закрываемая карта-наряд.
        certifying_staff (DataBaseUser): Специалист подтверждающего персонала.
        user_ip (str): IP-адрес инициатора закрытия для журнала аудита.

    Returns:
        MaintenanceReleaseCertificate: Оформленное Свидетельство о выполнении ТО ВС (CRS).

    Raises:
        ValidationError: При несоблюдении любого из обязательных требований ФАП-145.
    """
    card = OutfitCard.objects.select_for_update().get(pk=outfit_card.pk)

    if card.is_signed and card.crs_certificates.exists():
        logger.warning("Outfit card %s already released and signed.", card.pk)
        return card.crs_certificates.first()

    card.certifying_staff = certifying_staff

    # Комплексная проверка готовности
    is_valid, errors = validate_outfit_card_for_release(card)
    if not is_valid:
        error_msg = "Отказ в закрытии наряда и выпуске CRS (ФАП-145):\n- " + "\n- ".join(errors)
        logger.error("Release validation failed for card %s: %s", card.pk, error_msg)
        raise ValidationError(error_msg)

    # Установка даты окончания ТО, если не была указана
    if not card.outfit_card_date_end:
        card.outfit_card_date_end = timezone.now().date()

    # Генерация контрольной суммы неизменяемости (п. 40 ФАП-145)
    card.is_signed = True
    card.signed_at = timezone.now()
    card.signature_hash = calculate_outfit_card_release_hash(card)
    card.save()

    # Создание или актуализация Свидетельства о ТО ВС (CRS)
    certificate = MaintenanceReleaseCertificate.create_from_outfit_card(
        outfit_card=card,
        certifying_staff=certifying_staff,
        issue_date=card.outfit_card_date_end,
    )

    logger.info(
        "Outfit card %s successfully released with CRS %s by staff %s (IP: %s)",
        card.pk,
        certificate.certificate_number,
        certifying_staff.pk,
        user_ip,
    )
    return certificate
