"""Сервисный слой учета привлеченных организаций и агрегатов (ФАП-367, Разделы IV и XV).

Модуль инкапсулирует бизнес-логику:
- Контроля легитимности привлеченных организаций по ТО компонентов (наличие действующего
  сертификата ФАВТ на дату выполнения ТО воздушного судна согласно п. 96 ФАП-367);
- Проверки обязательного наличия входящих документов о годности (Талон годности по форме
  Приложения № 2 к ФАП-367 / Form 1, паспортов или этикеток заводов по п. 28 ФАП-367);
- Мониторинга приближения срока окончания сертификатов привлеченных организаций;
- Фиксации технологических операций монтажа/демонтажа агрегатов в картах-нарядах с
  автоматическим обновлением статусов компонентов и привязки к воздушным судам.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from contracts_app.models import Estate
from hrdepartment_app.models import (
    AviationComponent,
    AviationComponentStatus,
    ComponentOperationType,
    ExternalMaintenanceOrganization,
    OutfitCard,
    OutfitCardComponent,
)

logger = logging.getLogger(__name__)


def validate_component_for_installation(
    component: AviationComponent,
    outfit_card_date: Optional[datetime.date] = None,
) -> Tuple[bool, Optional[str]]:
    """Проверяет возможность установки авиационного компонента на воздушное судно.

    В соответствии с п. 28 и п. 96 ФАП-367 проверяются:
    1. Наличие входящего документа о годности (номер и дата Талона годности/паспорта);
    2. Легитимность привлеченной организации, выполнившей ТО/ремонт агрегата
       (активный статус и не истекший срок действия сертификата ТО на дату проведения работ).

    Args:
        component: Проверяемый авиационный компонент (AviationComponent).
        outfit_card_date: Дата проведения работ по наряду (по умолчанию текущая дата).

    Returns:
        Tuple[bool, Optional[str]]: Кортеж (успех, сообщение_об_ошибке).
            При успешной валидации возвращает (True, None).
    """
    check_date = outfit_card_date or datetime.date.today()

    # 1. Проверка наличия входящего документа о годности
    if not component.release_doc_number or not component.release_doc_number.strip():
        msg = (
            f"Компонент '{component.name}' (черт. № {component.part_number}, зав. № {component.serial_number}) "
            "не имеет входящего документа о годности (Талон годности по Приложению № 2 к ФАП-367, "
            "паспорт агрегата или этикетка завода-изготовителя). Установка на ВС запрещена (п. 28 ФАП-367)."
        )
        return False, msg

    # 2. Проверка сертификата привлеченной организации
    if component.last_repair_org:
        org = component.last_repair_org
        if not org.is_certificate_valid(check_date):
            valid_to_str = (
                f"{org.certificate_valid_until:%d.%m.%Y}"
                if org.certificate_valid_until
                else "отозван / не активен"
            )
            msg = (
                f"Сертификат организации '{org.short_name}' (№ {org.certificate_number}), "
                f"выполнившей ТО компонента '{component.name}', недействителен на дату ТО {check_date:%d.%m.%Y} "
                f"(срок действия: {valid_to_str}). "
                "Согласно п. 96 ФАП-367, установка компонентов от организаций без действующего сертификата запрещена."
            )
            return False, msg

    return True, None


def get_expiring_subcontractor_certificates(
    days_threshold: int = 30,
) -> List[Dict[str, Any]]:
    """Возвращает список привлеченных организаций с истекающими или просроченными сертификатами.

    Используется для предупреждающего контроля качества (QA) и дашбордов руководства.

    Args:
        days_threshold: Пороговое количество дней до окончания срока действия (по умолчанию 30).

    Returns:
        List[Dict[str, Any]]: Список словарей с реквизитами организаций и статусом срочности:
            - 'org': экземпляр ExternalMaintenanceOrganization;
            - 'days_left': оставшееся число дней (отрицательное, если просрочен);
            - 'is_expired': флаг истечения срока действия;
            - 'urgency': классификация ('expired', 'warning', 'ok').
    """
    today = datetime.date.today()
    target_date = today + datetime.timedelta(days=days_threshold)

    # Выбираем организации с установленным сроком действия, который меньше пороговой даты
    orgs = ExternalMaintenanceOrganization.objects.filter(
        certificate_valid_until__isnull=False,
        certificate_valid_until__lte=target_date,
    ).order_by("certificate_valid_until")

    result: List[Dict[str, Any]] = []
    for org in orgs:
        if not org.certificate_valid_until:
            continue
        days_left = (org.certificate_valid_until - today).days
        is_expired = days_left < 0
        urgency = "expired" if is_expired else ("warning" if days_left <= days_threshold else "ok")

        result.append({
            "org": org,
            "days_left": days_left,
            "is_expired": is_expired,
            "urgency": urgency,
        })

    return result


def get_aircraft_installed_components(
    air_board: Estate,
) -> QuerySet[AviationComponent]:
    """Возвращает список компонентов, смонтированных на указанном воздушном судне.

    Args:
        air_board: Экземпляр воздушного судна (Estate).

    Returns:
        QuerySet[AviationComponent]: Набор установленных компонентов.
    """
    return AviationComponent.objects.filter(
        current_aircraft=air_board,
        status=AviationComponentStatus.INSTALLED,
    ).select_related("last_repair_org", "aircraft_type")


@transaction.atomic
def register_component_operation(
    outfit_card: OutfitCard,
    operation_type: str,
    installed_component: Optional[AviationComponent] = None,
    removed_component_name: str = "",
    removed_part_number: str = "",
    removed_serial_number: str = "",
    removal_reason: str = "Плановая замена по выработке ресурса",
    installed_position: str = "",
    operating_hours_on_install: Optional[Any] = None,
    notes: str = "",
) -> OutfitCardComponent:
    """Транзакционно регистрирует установку или демонтаж компонента в карте-наряде.

    Выполняет полную нормативную валидацию по ФАП-367 и обновляет состояние агрегатов.

    Args:
        outfit_card: Карта-наряд на выполнение ТО.
        operation_type: Тип операции ('install', 'remove', 'replace').
        installed_component: Устанавливаемый компонент (обязателен для install и replace).
        removed_component_name: Наименование снятого агрегата.
        removed_part_number: Чертежный номер снятого агрегата (P/N).
        removed_serial_number: Заводской номер снятого агрегата (S/N).
        removal_reason: Причина снятия компонента.
        installed_position: Место установки на борту ВС.
        operating_hours_on_install: Наработка ВС на момент установки.
        notes: Дополнительные служебные примечания.

    Returns:
        OutfitCardComponent: Созданная запись операции в карте-наряде.

    Raises:
        ValidationError: При нарушении требований ФАП-367.
    """
    card_date = outfit_card.outfit_card_date or datetime.date.today()

    if operation_type in (ComponentOperationType.INSTALL, ComponentOperationType.REPLACE):
        if not installed_component:
            raise ValidationError({
                "installed_component": "При операции установки или замены необходимо выбрать устанавливаемый агрегат."
            })

        is_valid, err_msg = validate_component_for_installation(installed_component, card_date)
        if not is_valid:
            logger.warning("Отказ установки компонента: %s (наряд %s)", err_msg, outfit_card.pk)
            raise ValidationError({"installed_component": err_msg})

    op = OutfitCardComponent.objects.create(
        outfit_card=outfit_card,
        operation_type=operation_type,
        installed_component=installed_component,
        removed_component_name=removed_component_name,
        removed_part_number=removed_part_number,
        removed_serial_number=removed_serial_number,
        removal_reason=removal_reason,
        installed_position=installed_position,
        operating_hours_on_install=operating_hours_on_install or outfit_card.flight_hours,
        notes=notes,
    )

    # Если компонент установлен, обновляем его статус и текущий борт
    if installed_component and operation_type in (ComponentOperationType.INSTALL, ComponentOperationType.REPLACE):
        installed_component.status = AviationComponentStatus.INSTALLED
        installed_component.current_aircraft = outfit_card.air_board
        installed_component.save(update_fields=["status", "current_aircraft", "updated_at"])

    return op
