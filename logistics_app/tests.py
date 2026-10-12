"""Unit-тесты для подсистемы электронного документооборота (СЭД) logistics_app."""

import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from unittest.mock import patch

from decimal import Decimal
import datetime
from django.urls import reverse

from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity
from logistics_app.models import (
    DocFlowApprovalLog,
    DocFlowDocument,
    DocFlowDocumentType,
    DocFlowFile,
    DocFlowFileVersion,
    DocFlowNumberCounter,
    DocFlowRouteStep,
    DocFlowRouteStepTemplate,
    DocFlowRouteTemplate,
    Package,
    PackageEventLog,
    PackageImage,
    PackageItem,
    ShipmentCounter,
    ShipmentTrip,
    TripStop,
)
from logistics_app.services.docflow_notification_service import DocFlowNotificationService
from logistics_app.services.docflow_routing_service import DocFlowRoutingService
from logistics_app.services.docflow_version_service import DocFlowVersionService
from logistics_app.forms import InternalPackageForm
from logistics_app.services import (
    PackageService,
    PackageSheetGenerator,
    ShipmentTripService,
)


class DocFlowServicesTestCase(TestCase):
    """Набор тестов для проверки бизнес-логики и сервисного слоя СЭД."""

    def setUp(self) -> None:
        """Подготовка тестовых данных."""
        self.email_patcher = patch(
            "mailbox_app.services.email_service.UniversalEmailService.send_async_email",
            return_value=True,
        )
        self.email_patcher.start()
        self.addCleanup(self.email_patcher.stop)

        self.division = Division.objects.create(name="Юридический отдел", code="LAW_01")
        self.initiator = DataBaseUser.objects.create_user(
            username="initiator_user",
            password="testpassword123",
            email="initiator@barkol.ru",
            first_name="Иван",
            last_name="Инициаторов",
        )
        self.reviewer_1 = DataBaseUser.objects.create_user(
            username="reviewer_1",
            password="testpassword123",
            email="lawyer@barkol.ru",
            first_name="Петр",
            last_name="Юристов",
        )
        self.reviewer_2 = DataBaseUser.objects.create_user(
            username="reviewer_2",
            password="testpassword123",
            email="accountant@barkol.ru",
            first_name="Анна",
            last_name="Бухгалтерова",
        )

        self.doc_type = DocFlowDocumentType.objects.create(
            name="Исходящий договор аренды ВС",
            category=DocFlowDocumentType.Category.OUTBOUND,
            code="OUT_AIRCRAFT_LEASE",
            default_sla_hours=48,
        )

        # Создаем шаблон маршрута: Шаг 1 (Юрист) -> Шаг 2 (Бухгалтер)
        self.template = DocFlowRouteTemplate.objects.create(
            name="Стандартный маршрут договора",
            doc_type=self.doc_type,
            is_default=True,
        )
        self.step_tmpl_1 = DocFlowRouteStepTemplate.objects.create(
            route_template=self.template,
            step_order=1,
            step_name="Согласование ЮО",
            step_type=DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
            assigned_user=self.reviewer_1,
            sla_hours=24,
            can_rollback_to=True,
        )
        self.step_tmpl_2 = DocFlowRouteStepTemplate.objects.create(
            route_template=self.template,
            step_order=2,
            step_name="Визирование Бухгалтерией",
            step_type=DocFlowRouteStepTemplate.StepType.SEQUENTIAL,
            assigned_user=self.reviewer_2,
            sla_hours=24,
            can_rollback_to=True,
        )

        # Создаем тестовый документ
        self.document = DocFlowDocument.objects.create(
            doc_type=self.doc_type,
            title="Проект договора аренды Ми-8 №124",
            initiator=self.initiator,
            status=DocFlowDocument.Status.DRAFT,
        )

    def test_number_counter_generation(self) -> None:
        """Проверка корректности автогенерации регистрационных номеров по стандарту."""
        num_1 = DocFlowNumberCounter.generate_number(DocFlowDocumentType.Category.INBOUND, year=2026)
        num_2 = DocFlowNumberCounter.generate_number(DocFlowDocumentType.Category.INBOUND, year=2026)
        num_out = DocFlowNumberCounter.generate_number(DocFlowDocumentType.Category.OUTBOUND, year=2026)

        self.assertEqual(num_1, "СЭД-ВХ-2026/00001")
        self.assertEqual(num_2, "СЭД-ВХ-2026/00002")
        self.assertEqual(num_out, "СЭД-ИС-2026/00001")

    def test_build_route_and_start_approval(self) -> None:
        """Проверка построения маршрута из шаблона и активации первого шага."""
        steps = DocFlowRoutingService.build_route_from_template(self.document)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_name, "Согласование ЮО")
        self.assertEqual(steps[0].status, DocFlowRouteStep.Status.PENDING)

        started_doc = DocFlowRoutingService.start_approval_process(self.document, self.initiator)
        self.assertEqual(started_doc.status, DocFlowDocument.Status.ON_APPROVAL)
        self.assertTrue(started_doc.reg_number.startswith("СЭД-ИС-"))

        first_step = started_doc.route_steps.get(step_order=1)
        self.assertEqual(first_step.status, DocFlowRouteStep.Status.IN_PROGRESS)
        self.assertIsNotNone(first_step.started_at)
        self.assertIsNotNone(first_step.due_date)

    def test_approval_flow_and_completion(self) -> None:
        """Проверка полного сквозного цикла визирования документа."""
        DocFlowRoutingService.build_route_from_template(self.document)
        DocFlowRoutingService.start_approval_process(self.document, self.initiator)

        step_1 = self.document.route_steps.get(step_order=1)
        result_1 = DocFlowRoutingService.process_approval(
            document=self.document,
            step=step_1,
            user=self.reviewer_1,
            comment="Юридических замечаний нет",
        )
        self.assertEqual(result_1["status"], "next_step")

        step_1.refresh_from_db()
        self.assertEqual(step_1.status, DocFlowRouteStep.Status.APPROVED)

        step_2 = self.document.route_steps.get(step_order=2)
        self.assertEqual(step_2.status, DocFlowRouteStep.Status.IN_PROGRESS)

        result_2 = DocFlowRoutingService.process_approval(
            document=self.document,
            step=step_2,
            user=self.reviewer_2,
            comment="Фин. условия подтверждены",
        )
        self.assertEqual(result_2["status"], "completed")

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, DocFlowDocument.Status.APPROVED)

    def test_rollback_to_previous_step(self) -> None:
        """Проверка механизма отката на выбранный предшествующий шаг."""
        DocFlowRoutingService.build_route_from_template(self.document)
        DocFlowRoutingService.start_approval_process(self.document, self.initiator)

        step_1 = self.document.route_steps.get(step_order=1)
        DocFlowRoutingService.process_approval(self.document, step_1, self.reviewer_1)

        step_2 = self.document.route_steps.get(step_order=2)
        self.assertEqual(step_2.status, DocFlowRouteStep.Status.IN_PROGRESS)

        # Бухгалтер замечает ошибку в расчетах юриста и делает откат на Шаг 1
        DocFlowRoutingService.process_rollback(
            document=self.document,
            step=step_2,
            user=self.reviewer_2,
            target_step_order=1,
            comment="Проверьте ставку НДС в пункте 4.2",
        )

        step_2.refresh_from_db()
        self.assertEqual(step_2.status, DocFlowRouteStep.Status.RETURNED)

        step_1.refresh_from_db()
        self.assertEqual(step_1.status, DocFlowRouteStep.Status.IN_PROGRESS)

        self.document.refresh_from_db()
        self.assertEqual(self.document.current_step_order, 1)

    def test_version_service_upload_and_increment(self) -> None:
        """Проверка версионирования файлов, вычисления SHA-256 и инкремента версии."""
        doc_file = DocFlowFile.objects.create(
            document=self.document,
            title="Договор_аренды.docx",
            current_version_number="1.0",
        )

        sample_content = b"Contract version 1.0 binary content"
        uploaded_file = SimpleUploadedFile("contract_v1.docx", sample_content)

        ver_1 = DocFlowVersionService.upload_new_file_version(
            doc_file=doc_file,
            file_obj=uploaded_file,
            user=self.initiator,
            comment="Первоначальная редакция",
            is_reviewer_edit=False,
        )
        self.assertEqual(ver_1.version_number, "2.0")
        self.assertTrue(len(ver_1.file_hash) == 64)

        # Редакционная правка согласующего юриста
        sample_content_rev = b"Contract version 2.1 modified by reviewer"
        uploaded_file_rev = SimpleUploadedFile("contract_v2_1.docx", sample_content_rev)
        ver_2 = DocFlowVersionService.upload_new_file_version(
            doc_file=doc_file,
            file_obj=uploaded_file_rev,
            user=self.reviewer_1,
            comment="Исправлена формулировка ответственности",
            is_reviewer_edit=True,
        )
        self.assertEqual(ver_2.version_number, "2.1")
        self.assertTrue(ver_2.is_reviewer_edit)

    def test_pdf_approval_sheet_generation(self) -> None:
        """Проверка генерации официального PDF-листа согласования с ПЭП."""
        from logistics_app.services.docflow_sheet_service import DocFlowSheetGenerator

        DocFlowRoutingService.build_route_from_template(self.document)
        DocFlowRoutingService.start_approval_process(self.document, self.initiator)

        step_1 = self.document.route_steps.get(step_order=1)
        DocFlowRoutingService.process_approval(
            document=self.document,
            step=step_1,
            user=self.reviewer_1,
            comment="Согласовано юристом",
        )

        pdf_bytes = DocFlowSheetGenerator.generate_approval_sheet_pdf(self.document)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_sla_deadlines_celery_task(self) -> None:
        """Проверка выполнения фоновой задачи мониторинга дедлайнов SLA."""
        from logistics_app.tasks import check_docflow_sla_deadlines_task

        DocFlowRoutingService.build_route_from_template(self.document)
        DocFlowRoutingService.start_approval_process(self.document, self.initiator)

        # Вызываем таску напрямую (без брокера)
        count = check_docflow_sla_deadlines_task()
        self.assertIsInstance(count, int)

    def test_dynamic_initial_route_without_template(self) -> None:
        """Проверка динамического создания первичного маршрута без шаблона."""
        # Создаем документ с типом, для которого нет шаблонов
        doc_type_no_tpl = DocFlowDocumentType.objects.create(
            name="Служебная записка без шаблона",
            code="MEMO_NO_TPL",
            category=DocFlowDocumentType.Category.INTERNAL,
        )
        doc = DocFlowDocument.objects.create(
            doc_type=doc_type_no_tpl,
            title="Заявка на доступ к сервису",
            initiator=self.initiator,
            status=DocFlowDocument.Status.DRAFT,
        )

        # 1. Запуск с явным указанием согласующего руководителя
        steps = DocFlowRoutingService.create_dynamic_initial_route(
            document=doc,
            approver=self.reviewer_1,
            sla_hours=24,
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].assigned_user, self.reviewer_1)
        self.assertEqual(steps[0].step_order, 1)

        # 2. Запуск процесса согласования
        started_doc = DocFlowRoutingService.start_approval_process(
            document=doc,
            user=self.initiator,
            first_approver=self.reviewer_1,
        )
        self.assertEqual(started_doc.status, DocFlowDocument.Status.ON_APPROVAL)
        first_step = started_doc.route_steps.get(step_order=1)
        self.assertEqual(first_step.status, DocFlowRouteStep.Status.IN_PROGRESS)

    def test_ad_hoc_step_add_and_delete(self) -> None:
        """Проверка добавления и удаления произвольных этапов в черновике."""
        doc = DocFlowDocument.objects.create(
            doc_type=self.doc_type,
            title="Служебная записка о закупке",
            initiator=self.initiator,
            status=DocFlowDocument.Status.DRAFT,
        )

        step_1 = DocFlowRoutingService.add_ad_hoc_step(
            document=doc,
            step_name="Визирование начальником отдела",
            assigned_user=self.reviewer_1,
            sla_hours=24,
        )
        self.assertEqual(step_1.step_order, 1)

        step_2 = DocFlowRoutingService.add_ad_hoc_step(
            document=doc,
            step_name="Исполнение отделом закупок",
            assigned_user=self.reviewer_2,
            sla_hours=48,
        )
        self.assertEqual(step_2.step_order, 2)
        self.assertEqual(doc.route_steps.count(), 2)

        # Удаление шага
        deleted = DocFlowRoutingService.remove_ad_hoc_step(doc, step_id=step_1.id)
        self.assertTrue(deleted)
        self.assertEqual(doc.route_steps.count(), 1)
        remaining_step = doc.route_steps.first()
        self.assertEqual(remaining_step.step_order, 1)

    def test_dynamic_executor_assignment_on_approval(self) -> None:
        """Проверка назначения исполнителя руководителем в момент согласования."""
        doc = DocFlowDocument.objects.create(
            doc_type=self.doc_type,
            title="Служебная записка с динамическим назначением",
            initiator=self.initiator,
            status=DocFlowDocument.Status.DRAFT,
        )

        # Создаем 1-й шаг на руководителя
        DocFlowRoutingService.create_dynamic_initial_route(
            document=doc,
            approver=self.reviewer_1,
            sla_hours=24,
        )
        DocFlowRoutingService.start_approval_process(document=doc, user=self.initiator)

        step_1 = doc.route_steps.get(step_order=1)
        self.assertEqual(step_1.status, DocFlowRouteStep.Status.IN_PROGRESS)

        # Руководитель визирует и назначает исполнителя reviewer_2
        res = DocFlowRoutingService.process_approval(
            document=doc,
            step=step_1,
            user=self.reviewer_1,
            comment="Согласовано. Направить на исполнение.",
            next_step_action="ASSIGN_EXECUTOR",
            next_executor=self.reviewer_2,
            next_step_name="Исполнение задачи",
            next_sla_hours=48,
            next_step_instructions="Предоставить доступ до конца недели",
        )

        self.assertEqual(res["status"], "next_step")
        step_1.refresh_from_db()
        self.assertEqual(step_1.status, DocFlowRouteStep.Status.APPROVED)

        # Проверяем, что автоматически создался и активировался Шаг 2 на reviewer_2
        step_2 = doc.route_steps.get(step_order=2)
        self.assertEqual(step_2.assigned_user, self.reviewer_2)
        self.assertEqual(step_2.step_name, "Исполнение задачи")
        self.assertEqual(step_2.status, DocFlowRouteStep.Status.IN_PROGRESS)

        # Исполнитель завершает задачу
        res_2 = DocFlowRoutingService.process_approval(
            document=doc,
            step=step_2,
            user=self.reviewer_2,
            comment="Задача выполнена, доступ предоставлен.",
            next_step_action="AUTO",
        )
        self.assertEqual(res_2["status"], "completed")

        doc.refresh_from_db()
        self.assertEqual(doc.status, DocFlowDocument.Status.APPROVED)


class ShipmentServicesTestCase(TestCase):
    """Набор тестов для проверки бизнес-логики рейсов, посылок, описи и приемки на МПД."""

    def setUp(self) -> None:
        """Подготовка тестовых сущностей пользователей, МПД и подразделений."""
        self.user_dispatcher = DataBaseUser.objects.create_user(
            username="dispatcher_user",
            password="testpassword123",
            first_name="Алексей",
            last_name="Логистов",
        )
        self.user_driver = DataBaseUser.objects.create_user(
            username="driver_user",
            password="testpassword123",
            first_name="Иван",
            last_name="Шоферов",
        )
        self.user_sender = DataBaseUser.objects.create_user(
            username="sender_user",
            password="testpassword123",
            first_name="Сергей",
            last_name="Отправителев",
        )
        self.user_receiver = DataBaseUser.objects.create_user(
            username="receiver_user",
            password="testpassword123",
            first_name="Дмитрий",
            last_name="Получателев",
        )

        self.mpd_surgut = PlaceProductionActivity.objects.create(name="МПД «Сургут»")
        self.mpd_noyabrsk = PlaceProductionActivity.objects.create(name="МПД «Ноябрьск»")

    def test_shipment_counter_generation(self) -> None:
        """Проверяет генерацию номеров рейсов и трек-номеров посылок с инкрементом."""
        trip_num_1 = ShipmentCounter.generate_number("TRIP", year=2026)
        trip_num_2 = ShipmentCounter.generate_number("TRIP", year=2026)
        self.assertEqual(trip_num_1, "РЕЙС-2026/0001")
        self.assertEqual(trip_num_2, "РЕЙС-2026/0002")

        pkg_num_1 = ShipmentCounter.generate_number("PACKAGE", year=2026)
        pkg_num_2 = ShipmentCounter.generate_number("PACKAGE", year=2026)
        self.assertEqual(pkg_num_1, "ПКГ-2026/00001")
        self.assertEqual(pkg_num_2, "ПКГ-2026/00002")

    def test_trip_full_lifecycle(self) -> None:
        """Проверяет полный жизненный цикл рейса: создание, привязка посылок, выезд, прибытие на МПД и завершение."""
        today = datetime.date.today()

        # 1. Создание рейса
        trip = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=today,
            origin_custom="Центральный склад (Москва)",
            destinations=[self.mpd_surgut, self.mpd_noyabrsk],
            vehicle_type=ShipmentTrip.VehicleType.COMPANY_CAR,
            vehicle_model="ГАЗель Next",
            vehicle_reg_number="А123БВ 777",
            driver_user=self.user_driver,
            comment="Срочная доставка запчастей",
        )
        self.assertTrue(trip.trip_number.startswith("РЕЙС-"))
        self.assertEqual(trip.status, ShipmentTrip.Status.PLANNING)
        self.assertEqual(trip.stops.count(), 2)

        # 2. Создание двух посылок (одна на Сургут, вторая на Ноябрьск)
        pkg_surgut = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            recipient=self.user_receiver,
            trip=trip,
            urgency=Package.Urgency.URGENT,
            package_type=Package.PackageType.BOX,
            places_count=1,
            items_data=[
                {"name": "Датчик давления", "part_number": "DPS-100", "quantity_sent": 2, "unit": "шт."},
                {"name": "Комплект прокладок", "part_number": "GSK-45", "quantity_sent": 5, "unit": "компл."},
            ],
        )
        self.assertEqual(pkg_surgut.status, Package.Status.ASSIGNED_TO_TRIP)
        self.assertEqual(pkg_surgut.items.count(), 2)

        pkg_noyabrsk = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_noyabrsk,
            recipient=self.user_receiver,
            trip=trip,
            urgency=Package.Urgency.NORMAL,
            package_type=Package.PackageType.PALLET,
            places_count=1,
            items_data=[
                {"name": "Блок управления", "part_number": "ECU-90", "quantity_sent": 1, "unit": "шт."},
            ],
        )
        self.assertEqual(trip.packages.count(), 2)

        # 3. Консолидация рейса
        ShipmentTripService.consolidate_trip(trip, self.user_dispatcher)
        trip.refresh_from_db()
        self.assertEqual(trip.status, ShipmentTrip.Status.CONSOLIDATED)

        # 4. Отправка машины в рейс (выезд)
        ShipmentTripService.start_trip(trip, self.user_dispatcher)
        trip.refresh_from_db()
        self.assertEqual(trip.status, ShipmentTrip.Status.IN_TRANSIT)
        self.assertIsNotNone(trip.actual_departure_at)

        # Посылки автоматически перешли в IN_TRANSIT
        pkg_surgut.refresh_from_db()
        pkg_noyabrsk.refresh_from_db()
        self.assertEqual(pkg_surgut.status, Package.Status.IN_TRANSIT)
        self.assertEqual(pkg_noyabrsk.status, Package.Status.IN_TRANSIT)

        # 5. Прибытие на первую точку (Сургут)
        ShipmentTripService.arrive_at_stop(trip, self.mpd_surgut, self.user_driver)
        pkg_surgut.refresh_from_db()
        pkg_noyabrsk.refresh_from_db()

        # Посылка в Сургут перешла в статус ожидания приемки на МПД
        self.assertEqual(pkg_surgut.status, Package.Status.DELIVERED_AT_MPD)
        # Посылка в Ноябрьск осталась в пути
        self.assertEqual(pkg_noyabrsk.status, Package.Status.IN_TRANSIT)

        # 6. Приемка груза на МПД Сургут в полном объеме
        items_rec = [
            {"id": item.id, "quantity_received": item.quantity_sent, "item_status": PackageItem.ItemStatus.ACCEPTED}
            for item in pkg_surgut.items.all()
        ]
        PackageService.receive_package_on_mpd(
            package=pkg_surgut,
            user=self.user_receiver,
            items_reception=items_rec,
            reception_comment="Все места целы, замечаний нет.",
        )
        pkg_surgut.refresh_from_db()
        self.assertEqual(pkg_surgut.status, Package.Status.RECEIVED_FULL)
        self.assertFalse(pkg_surgut.has_discrepancy)
        self.assertIsNotNone(pkg_surgut.received_at)
        self.assertEqual(pkg_surgut.received_by, self.user_receiver)

        # 7. Прибытие на вторую точку (Ноябрьск) и приемка с недостачей
        ShipmentTripService.arrive_at_stop(trip, self.mpd_noyabrsk, self.user_driver)
        pkg_noyabrsk.refresh_from_db()
        self.assertEqual(pkg_noyabrsk.status, Package.Status.DELIVERED_AT_MPD)

        item_ecu = pkg_noyabrsk.items.first()
        PackageService.receive_package_on_mpd(
            package=pkg_noyabrsk,
            user=self.user_receiver,
            items_reception=[
                {
                    "id": item_ecu.id,
                    "quantity_received": 0,
                    "item_status": PackageItem.ItemStatus.SHORTAGE,
                    "discrepancy_comment": "Коробка вскрыта, блок отсутствует",
                }
            ],
            reception_comment="Составлен коммерческий акт недостачи № 12",
        )
        pkg_noyabrsk.refresh_from_db()
        self.assertEqual(pkg_noyabrsk.status, Package.Status.RECEIVED_WITH_DISCREPANCY)
        self.assertTrue(pkg_noyabrsk.has_discrepancy)

        # 8. Завершение рейса
        ShipmentTripService.complete_trip(trip, self.user_dispatcher)
        trip.refresh_from_db()
        self.assertEqual(trip.status, ShipmentTrip.Status.COMPLETED)
        self.assertIsNotNone(trip.actual_completed_at)

    def test_cancel_trip_returns_packages_to_queue(self) -> None:
        """Проверяет, что при отмене рейса посылки автоматически возвращаются в очередь ожидания."""
        trip = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=datetime.date.today(),
            destinations=[self.mpd_surgut],
        )
        pkg = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            trip=trip,
        )
        self.assertEqual(pkg.status, Package.Status.ASSIGNED_TO_TRIP)

        ShipmentTripService.cancel_trip(trip, self.user_dispatcher, reason="Поломка ТС")
        trip.refresh_from_db()
        pkg.refresh_from_db()

        self.assertEqual(trip.status, ShipmentTrip.Status.CANCELLED)
        self.assertIsNone(pkg.trip)
        self.assertEqual(pkg.status, Package.Status.AWAITING_SHIPMENT)

    def test_package_pdf_generation(self) -> None:
        """Проверяет корректность генерации PDF-описи вложения с QR-кодом."""
        pkg = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[
                {"name": "Вал приводной", "part_number": "SH-789", "serial_number": "SN-001", "quantity_sent": 1, "unit": "шт."},
            ],
        )
        pdf_bytes = PackageSheetGenerator.generate_pdf(pkg)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_package_views_http(self) -> None:
        """Проверяет доступность контроллеров представлений рейсов и посылок."""
        self.client.force_login(self.user_dispatcher)

        # Реестр рейсов
        resp_trips = self.client.get(reverse("logistics_app:trip_list"))
        self.assertEqual(resp_trips.status_code, 200)

        # Реестр посылок
        resp_packages = self.client.get(reverse("logistics_app:package_list"))
        self.assertEqual(resp_packages.status_code, 200)

        # Создание посылки через View
        pkg = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[{"name": "Болт", "quantity_sent": 10, "unit": "шт."}],
        )

        # Карточка посылки
        resp_detail = self.client.get(reverse("logistics_app:package_detail", kwargs={"pk": pkg.pk}))
        self.assertEqual(resp_detail.status_code, 200)

        # Мобильный экран приемки
        resp_receive = self.client.get(reverse("logistics_app:package_receive", kwargs={"pk": pkg.pk}))
        self.assertEqual(resp_receive.status_code, 200)

        # Печать PDF
        resp_pdf = self.client.get(reverse("logistics_app:package_sheet_pdf", kwargs={"pk": pkg.pk}))
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf["Content-Type"], "application/pdf")

    def test_trips_for_destination_api(self) -> None:
        """Проверяет фильтрацию открытых будущих рейсов по МПД назначения через API."""
        self.client.force_login(self.user_dispatcher)
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        yesterday = today - datetime.timedelta(days=1)

        # 1. Будущий рейс на Сургут
        trip_future_surgut = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=tomorrow,
            destinations=[self.mpd_surgut],
        )

        # 2. Прошедший рейс на Сургут
        trip_past_surgut = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=yesterday,
            destinations=[self.mpd_surgut],
        )

        # 3. Будущий рейс только на Ноябрьск
        trip_future_noyabrsk = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=tomorrow,
            destinations=[self.mpd_noyabrsk],
        )

        # Запрос рейсов для Сургута
        resp = self.client.get(
            reverse("logistics_app:api_trips_for_destination"),
            {"mpd_id": self.mpd_surgut.pk},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        trip_ids = [t["id"] for t in data["trips"]]
        self.assertIn(trip_future_surgut.pk, trip_ids)
        self.assertNotIn(trip_past_surgut.pk, trip_ids)
        self.assertNotIn(trip_future_noyabrsk.pk, trip_ids)

        # Запрос для МПД, куда рейсов нет
        mpd_unknown = PlaceProductionActivity.objects.create(name="Неизвестный МПД")
        resp_empty = self.client.get(
            reverse("logistics_app:api_trips_for_destination"),
            {"mpd_id": mpd_unknown.pk},
        )
        self.assertEqual(resp_empty.status_code, 200)
        self.assertEqual(resp_empty.json()["trips"], [])

    def test_packages_for_trip_api(self) -> None:
        """Проверяет динамический подбор посылок из очереди под МПД маршрута и дату рейса."""
        self.client.force_login(self.user_dispatcher)
        today = datetime.date.today()
        planned_trip_date = today + datetime.timedelta(days=2)

        # 1. Посылка на Сургут, создана сегодня (дата <= даты рейса)
        pkg_surgut_ok = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[{"name": "Труба", "quantity_sent": 1}],
        )

        # 2. Посылка на Ноябрьск
        pkg_noyabrsk = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_noyabrsk,
            items_data=[{"name": "Клапан", "quantity_sent": 2}],
        )

        # 3. Посылка на Сургут с будущей датой оформления (позже даты рейса)
        future_date = planned_trip_date + datetime.timedelta(days=5)
        pkg_surgut_late = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[{"name": "Поздний груз", "quantity_sent": 1}],
        )
        Package.objects.filter(pk=pkg_surgut_late.pk).update(
            created_at=timezone.make_aware(datetime.datetime.combine(future_date, datetime.time.min))
        )

        # Запрос подбора для рейса на Сургут
        resp = self.client.get(
            reverse("logistics_app:api_packages_for_trip"),
            {
                "planned_date": planned_trip_date.strftime("%d.%m.%Y"),
                "mpd_ids": str(self.mpd_surgut.pk),
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        pkg_ids = [p["id"] for p in data["packages"]]
        self.assertIn(pkg_surgut_ok.pk, pkg_ids)
        self.assertNotIn(pkg_noyabrsk.pk, pkg_ids)
        self.assertNotIn(pkg_surgut_late.pk, pkg_ids)

    def test_internal_package_form_validation(self) -> None:
        """Проверяет валидацию формы посылки на соответствие рейса и МПД."""
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        yesterday = today - datetime.timedelta(days=1)

        trip_surgut = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=tomorrow,
            destinations=[self.mpd_surgut],
        )
        trip_noyabrsk = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=tomorrow,
            destinations=[self.mpd_noyabrsk],
        )
        trip_past = ShipmentTripService.create_trip(
            dispatcher=self.user_dispatcher,
            planned_date=yesterday,
            destinations=[self.mpd_surgut],
        )

        # 1. Корректные данные: рейс заезжает на выбранный МПД
        form_valid = InternalPackageForm(data={
            "destination": self.mpd_surgut.pk,
            "origin_custom": "Центральный склад",
            "trip": trip_surgut.pk,
            "places_count": 1,
            "urgency": Package.Urgency.NORMAL,
            "package_type": Package.PackageType.BOX,
        })
        self.assertTrue(form_valid.is_valid(), form_valid.errors)

        # 2. Несоответствие: рейс не заезжает на Сургут
        form_wrong_trip = InternalPackageForm(data={
            "destination": self.mpd_surgut.pk,
            "origin_custom": "Центральный склад",
            "trip": trip_noyabrsk.pk,
            "places_count": 1,
            "urgency": Package.Urgency.NORMAL,
            "package_type": Package.PackageType.BOX,
        })
        self.assertFalse(form_wrong_trip.is_valid())
        self.assertIn("trip", form_wrong_trip.errors)

        # 3. Прошедшая дата рейса
        form_past_trip = InternalPackageForm(data={
            "destination": self.mpd_surgut.pk,
            "origin_custom": "Центральный склад",
            "trip": trip_past.pk,
            "places_count": 1,
            "urgency": Package.Urgency.NORMAL,
            "package_type": Package.PackageType.BOX,
        })
        self.assertFalse(form_past_trip.is_valid())
        self.assertIn("trip", form_past_trip.errors)

    def test_trip_create_attaches_selected_packages(self) -> None:
        """Проверяет привязку подобранных посылок при создании рейса."""
        self.client.force_login(self.user_dispatcher)
        pkg_1 = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[{"name": "Посылка 1"}],
        )
        pkg_2 = PackageService.create_package(
            sender=self.user_sender,
            destination=self.mpd_surgut,
            items_data=[{"name": "Посылка 2"}],
        )

        today_str = datetime.date.today().strftime("%d.%m.%Y")
        post_data = {
            "planned_date": today_str,
            "origin_custom": "Центральный склад",
            "vehicle_type": ShipmentTrip.VehicleType.COMPANY_CAR,
            "vehicle_model": "ГАЗель",
            "vehicle_reg_number": "В123ОР 777",
            "driver_name": "Иванов И.И.",
            "driver_phone": "+7 999 000-00-00",
            "comment": "Тестовый рейс",
            # Формсет остановок
            "stops-TOTAL_FORMS": "1",
            "stops-INITIAL_FORMS": "0",
            "stops-MIN_NUM_FORMS": "0",
            "stops-MAX_NUM_FORMS": "1000",
            "stops-0-mpd": str(self.mpd_surgut.pk),
            "stops-0-stop_order": "1",
            "stops-0-comment": "",
            # Посылки для привязки
            "packages_selection_active": "1",
            "attach_packages": [str(pkg_1.pk), str(pkg_2.pk)],
        }

        resp = self.client.post(reverse("logistics_app:trip_add"), post_data)
        self.assertEqual(resp.status_code, 302)

        created_trip = ShipmentTrip.objects.latest("created_at")
        pkg_1.refresh_from_db()
        pkg_2.refresh_from_db()

        self.assertEqual(pkg_1.trip, created_trip)
        self.assertEqual(pkg_1.status, Package.Status.ASSIGNED_TO_TRIP)
        self.assertEqual(pkg_2.trip, created_trip)
        self.assertEqual(pkg_2.status, Package.Status.ASSIGNED_TO_TRIP)
        self.assertEqual(created_trip.packages.count(), 2)


