"""Сервисный слой сквозного поиска и быстрого создания номенклатуры грузов.

Обеспечивает интеллектуальный подбор мастер-позиций для описей вложений
по нескольким источникам: каталог грузов CargoItemCatalog, специнструмент
ТО ФАП-145 (MaintenanceEquipment), документы СЭД (DocFlowDocument) и
складская номенклатура (Nomenclature).
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from django.db.models import Q
from django.utils import timezone

from hrdepartment_app.models import MaintenanceEquipment
from logistics_app.models import (
    CargoCategory,
    CargoItemCatalog,
    DocFlowDocument,
    Nomenclature,
)


class CargoSearchService:
    """Сервис универсального сквозного поиска и управления номенклатурой грузов."""

    @classmethod
    def search(
        cls,
        query: str,
        category_code: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Выполняет сквозной интеллектуальный поиск номенклатуры по нескольким источникам.

        Args:
            query (str): Поисковая строка (наименование, чертежный номер, артикул, S/N, № документа).
            category_code (Optional[str]): Фильтр по коду категории груза (DOCUMENT, AIRCRAFT_PART и др.).
            limit (int): Максимальное совокупное число возвращаемых результатов. Defaults to 25.

        Returns:
            List[Dict[str, Any]]: Список найденных элементов в унифицированном формате для Select2 / автокомплита.
        """
        query = (query or "").strip()
        results: List[Dict[str, Any]] = []

        if not query and not category_code:
            # Если запрос пустой, отдаем топ популярных позиций из каталога
            catalog_qs = CargoItemCatalog.objects.filter(is_reusable=True).select_related("category")[:limit]
            for item in catalog_qs:
                results.append(cls._serialize_catalog_item(item))
            return results

        # 1. Поиск по мастер-каталогу грузов (CargoItemCatalog)
        catalog_q = Q(is_reusable=True)
        if category_code:
            catalog_q &= Q(category__code=category_code)
        if query:
            catalog_q &= (
                Q(name__icontains=query)
                | Q(part_number__icontains=query)
                | Q(article__icontains=query)
            )

        catalog_qs = (
            CargoItemCatalog.objects.filter(catalog_q)
            .select_related("category")
            .order_by("category__sort_order", "name")[:limit]
        )
        for item in catalog_qs:
            results.append(cls._serialize_catalog_item(item))

        remaining_slots = limit - len(results)
        if remaining_slots <= 0:
            return results

        # 2. Поиск по специнструменту ТО (MaintenanceEquipment), если категория не задана или TOOL_EQUIPMENT
        if not category_code or category_code == CargoCategory.Code.TOOL_EQUIPMENT:
            tool_q = Q()
            if query:
                tool_q = (
                    Q(name__icontains=query)
                    | Q(part_number__icontains=query)
                    | Q(serial_number__icontains=query)
                    | Q(marking_code__icontains=query)
                    | Q(inventory_number__icontains=query)
                )

            equipment_qs = (
                MaintenanceEquipment.objects.filter(tool_q)
                .select_related("production_place")
                .order_by("name")[:remaining_slots]
            )
            for eq in equipment_qs:
                results.append(cls._serialize_equipment(eq))

        remaining_slots = limit - len(results)
        if remaining_slots <= 0:
            return results

        # 3. Поиск по документам СЭД (DocFlowDocument), если категория не задана или DOCUMENT
        if not category_code or category_code == CargoCategory.Code.DOCUMENT:
            doc_q = Q()
            if query:
                doc_q = (
                    Q(reg_number__icontains=query)
                    | Q(title__icontains=query)
                    | Q(description__icontains=query)
                )

            docflow_qs = (
                DocFlowDocument.objects.filter(doc_q)
                .select_related("doc_type")
                .order_by("-created_at")[:remaining_slots]
            )
            for doc in docflow_qs:
                results.append(cls._serialize_docflow(doc))

        remaining_slots = limit - len(results)
        if remaining_slots <= 0:
            return results

        # 4. Поиск по складской номенклатуре (Nomenclature), если категория не задана или AIRCRAFT_PART / MATERIAL
        if not category_code or category_code in [
            CargoCategory.Code.AIRCRAFT_PART,
            CargoCategory.Code.MATERIAL_CHEMICAL,
        ]:
            nom_q = Q()
            if query:
                nom_q = (
                    Q(name__icontains=query)
                    | Q(serial_number__icontains=query)
                    | Q(description__icontains=query)
                )

            nom_qs = (
                Nomenclature.objects.filter(nom_q)
                .select_related("unit", "grade", "group")
                .order_by("name")[:remaining_slots]
            )
            for nom in nom_qs:
                results.append(cls._serialize_nomenclature(nom))

        return results[:limit]

    @classmethod
    def quick_create(
        cls,
        name: str,
        category_code: str,
        part_number: str = "",
        article: str = "",
        unit: str = "шт.",
        weight_kg: Optional[Decimal] = None,
        specifications: Optional[Dict[str, Any]] = None,
    ) -> CargoItemCatalog:
        """Создает новую мастер-позицию в каталоге номенклатуры грузов.

        Args:
            name (str): Наименование номенклатуры.
            category_code (str): Код существующей категории (DOCUMENT, AIRCRAFT_PART и др.).
            part_number (str, optional): Чертежный номер / P/N. Defaults to "".
            article (str, optional): Внутренний артикул. Defaults to "".
            unit (str, optional): Единица измерения. Defaults to "шт.".
            weight_kg (Optional[Decimal], optional): Ориентировочный вес. Defaults to None.
            specifications (Optional[Dict[str, Any]], optional): Словарь характеристик. Defaults to None.

        Returns:
            CargoItemCatalog: Созданный или найденный экземпляр каталога.

        Raises:
            ValueError: Если категория не найдена или наименование пустое.
        """
        name = name.strip()
        if not name:
            raise ValueError("Наименование номенклатуры обязательно для заполнения.")

        category = CargoCategory.objects.filter(code=category_code).first()
        if not category:
            category = CargoCategory.objects.filter(code=CargoCategory.Code.OTHER).first()
            if not category:
                category = CargoCategory.objects.create(
                    code=CargoCategory.Code.OTHER,
                    name="Прочие грузы",
                    icon="bx-package"
                )

        item = CargoItemCatalog.objects.create(
            category=category,
            name=name,
            part_number=part_number.strip(),
            article=article.strip(),
            default_unit=unit.strip() or "шт.",
            default_weight_kg=weight_kg,
            specifications=specifications or {},
            is_reusable=True,
        )
        return item

    @classmethod
    def _serialize_catalog_item(cls, item: CargoItemCatalog) -> Dict[str, Any]:
        """Сериализует позицию каталога CargoItemCatalog в формат ответа Select2."""
        text_parts = [f"[{item.category.name}] {item.name}"]
        if item.part_number:
            text_parts.append(f"(P/N: {item.part_number})")
        if item.article:
            text_parts.append(f"арт. {item.article}")

        return {
            "id": f"catalog_{item.id}",
            "source": "CATALOG",
            "catalog_id": item.id,
            "text": " ".join(text_parts),
            "name": item.name,
            "part_number": item.part_number,
            "serial_number": "",
            "article": item.article,
            "unit": item.default_unit,
            "weight_kg": float(item.default_weight_kg) if item.default_weight_kg else None,
            "category_code": item.category.code,
            "category_name": item.category.name,
            "category_icon": item.category.icon,
            "specifications": item.specifications or {},
            "badge": item.category.name,
            "badge_class": "badge bg-label-primary",
        }

    @classmethod
    def _serialize_equipment(cls, eq: MaintenanceEquipment) -> Dict[str, Any]:
        """Сериализует инструмент ТО MaintenanceEquipment в формат ответа Select2."""
        today = timezone.now().date()
        is_verified = (
            eq.next_verification_date is not None
            and eq.next_verification_date >= today
        )
        status_label = "Поверен (годен)" if is_verified else "Требуется поверка"
        badge_class = "badge bg-label-success" if is_verified else "badge bg-label-danger"

        sn_display = f"S/N: {eq.serial_number}" if eq.serial_number else "б/н"
        text = f"[Инструмент ТО] {eq.name} ({sn_display})"
        if eq.part_number:
            text += f" P/N: {eq.part_number}"
        if eq.next_verification_date:
            text += f" [Поверка до {eq.next_verification_date:%d.%m.%Y}]"

        specs = {
            "marking_code": eq.marking_code or "",
            "inventory_number": eq.inventory_number or "",
            "verification_status": status_label,
            "verification_until": eq.next_verification_date.strftime("%Y-%m-%d") if eq.next_verification_date else "",
            "arshin_number": eq.arshin_verification_number or "",
        }

        return {
            "id": f"equipment_{eq.id}",
            "source": "EQUIPMENT",
            "equipment_id": eq.id,
            "text": text,
            "name": eq.name,
            "part_number": eq.part_number or "",
            "serial_number": eq.serial_number or "",
            "unit": "шт.",
            "weight_kg": None,
            "category_code": CargoCategory.Code.TOOL_EQUIPMENT,
            "category_name": "Специнструмент и КПА (ФАП-145)",
            "category_icon": "bx-wrench",
            "specifications": specs,
            "badge": f"ТО {sn_display}",
            "badge_class": badge_class,
        }

    @classmethod
    def _serialize_docflow(cls, doc: DocFlowDocument) -> Dict[str, Any]:
        """Сериализует документ СЭД DocFlowDocument в формат ответа Select2."""
        doc_type_name = doc.doc_type.name if doc.doc_type else "Документ"
        doc_dt = doc.reg_date or (doc.created_at.date() if doc.created_at else None)
        dt_str = doc_dt.strftime("%d.%m.%Y") if doc_dt else ""
        reg_num = doc.reg_number or "б/н"
        text = f"[СЭД] {doc_type_name} № {reg_num}"
        if dt_str:
            text += f" от {dt_str}"
        if doc.title:
            text += f" — {doc.title[:50]}"

        specs = {
            "doc_type": doc_type_name,
            "doc_number": doc.reg_number or "",
            "doc_date": doc_dt.strftime("%Y-%m-%d") if doc_dt else "",
            "is_original": True,
        }

        return {
            "id": f"docflow_{doc.id}",
            "source": "DOCFLOW",
            "docflow_id": doc.id,
            "text": text,
            "name": f"{doc_type_name}: {doc.title or reg_num}",
            "part_number": "",
            "serial_number": "",
            "unit": "шт.",
            "weight_kg": None,
            "category_code": CargoCategory.Code.DOCUMENT,
            "category_name": "Документы и корреспонденция",
            "category_icon": "bx-file",
            "specifications": specs,
            "badge": f"СЭД № {reg_num}",
            "badge_class": "badge bg-label-info",
        }

    @classmethod
    def _serialize_nomenclature(cls, nom: Nomenclature) -> Dict[str, Any]:
        """Сериализует складскую номенклатуру Nomenclature в формат ответа Select2."""
        text_parts = [f"[Склад] {nom.name}"]
        if nom.serial_number:
            text_parts.append(f"(S/N: {nom.serial_number})")

        specs = {}
        if nom.grade:
            specs["grade"] = nom.grade.name

        return {
            "id": f"nomenclature_{nom.id}",
            "source": "NOMENCLATURE",
            "nomenclature_id": nom.id,
            "text": " ".join(text_parts),
            "name": nom.name,
            "part_number": "",
            "serial_number": nom.serial_number or "",
            "unit": nom.unit.short_name if nom.unit else "шт.",
            "weight_kg": float(nom.weight) if nom.weight else None,
            "category_code": CargoCategory.Code.AIRCRAFT_PART,
            "category_name": "Авиационные детали и АТИ",
            "category_icon": "bx-paper-plane",
            "specifications": specs,
            "badge": "Склад",
            "badge_class": "badge bg-label-success",
        }
