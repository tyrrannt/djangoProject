"""Unit-тесты для подсистемы электронного документооборота (СЭД) logistics_app."""

import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from customers_app.models import DataBaseUser, Division
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
)
from logistics_app.services.docflow_notification_service import DocFlowNotificationService
from logistics_app.services.docflow_routing_service import DocFlowRoutingService
from logistics_app.services.docflow_version_service import DocFlowVersionService


class DocFlowServicesTestCase(TestCase):
    """Набор тестов для проверки бизнес-логики и сервисного слоя СЭД."""

    def setUp(self) -> None:
        """Подготовка тестовых данных."""
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

