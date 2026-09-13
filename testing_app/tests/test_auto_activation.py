"""Тесты для сервиса автоматической активации мероприятий тестирования и Celery задач."""

from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from customers_app.models import DataBaseUser, Job, Division, DataBaseUserWorkProfile
from testing_app.models import (
    Testing,
    QuestionCategory,
    Question,
    AnswerOption,
    TestingGroup,
    TestingGroupPosition,
    TestingCategorySetting,
    TestingAssignment,
)
from testing_app.services.event_service import (
    auto_activate_scheduled_testings,
    ensure_default_groups_exist,
)
from testing_app.tasks import auto_activate_scheduled_testings_task


class AutoActivationTestingTests(TestCase):
    """Набор тестов для проверки логики автоматического перевода мероприятий в статус ACTIVE."""

    def setUp(self) -> None:
        """Подготовка тестовых данных: пользователь, должности, вопросы и категории."""
        self.user = DataBaseUser.objects.create_user(
            username="test_user",
            email="test_user@barkol.ru",
            password="testpassword123",
            first_name="Иван",
            last_name="Иванов",
        )
        self.division = Division.objects.create(name="Летная служба")
        self.job = Job.objects.create(name="Авиатехник")
        self.user.user_work_profile = DataBaseUserWorkProfile.objects.create(
            job=self.job,
            divisions=self.division,
        )
        self.user.save(update_fields=["user_work_profile"])

        # Категория и 20 активных вопросов с правильными ответами
        self.category = QuestionCategory.objects.create(name="Безопасность полетов", is_active=True)
        for i in range(25):
            q = Question.objects.create(
                category=self.category,
                text=f"Тестовый вопрос {i + 1}",
                status=Question.Status.ACTIVE,
            )
            AnswerOption.objects.create(question=q, text="Правильный ответ", order_num=1, is_correct=True)
            AnswerOption.objects.create(question=q, text="Неправильный ответ", order_num=2, is_correct=False)

    def _setup_valid_testing(
        self,
        title: str,
        status: str,
        event_start_datetime,
        start_datetime,
        end_datetime
    ) -> Testing:
        """Вспомогательный метод создания полностью готового к сдаче тестирования."""
        testing = Testing.objects.create(
            title=title,
            order_number="123-ОД",
            order_date=timezone.now().date(),
            order_name="О проведении аттестации",
            event_start_datetime=event_start_datetime,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            questions_count=20,
            passing_score_percentage=80,
            status=status,
            author=self.user,
        )
        g1, g2 = ensure_default_groups_exist(testing)
        TestingGroupPosition.objects.create(group=g1, job=self.job)

        TestingCategorySetting.objects.create(
            testing=testing,
            category=self.category,
            percentage=100,
            calculated_questions_count=20,
        )

        TestingAssignment.objects.create(
            testing=testing,
            group=g1,
            employee=self.user,
            assigned_job_title=self.job.name,
            assigned_division_title=self.division.name,
            assignment_type=TestingAssignment.AssignmentType.AUTO,
            status=TestingAssignment.Status.NOT_STARTED,
        )
        return testing

    @patch("testing_app.tasks.send_event_assignments_batch_task.delay")
    def test_auto_activate_scheduled_testings_success(self, mock_batch_delay) -> None:
        """Проверяет успешную активацию мероприятия, чья дата начала уже наступила."""
        now = timezone.now()
        # Мероприятие 1: дата начала наступила час назад
        testing_due = self._setup_valid_testing(
            title="Тестирование 1",
            status=Testing.Status.SCHEDULED,
            event_start_datetime=now - timedelta(hours=1),
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=5),
        )

        # Мероприятие 2: дата начала в будущем (через 3 дня)
        testing_future = self._setup_valid_testing(
            title="Тестирование 2 (Будущее)",
            status=Testing.Status.SCHEDULED,
            event_start_datetime=now + timedelta(days=3),
            start_datetime=now + timedelta(days=4),
            end_datetime=now + timedelta(days=10),
        )

        result = auto_activate_scheduled_testings()

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["activated_count"], 1)
        self.assertIn(testing_due.id, result["activated_ids"])
        self.assertEqual(len(result["errors"]), 0)

        testing_due.refresh_from_db()
        testing_future.refresh_from_db()

        self.assertEqual(testing_due.status, Testing.Status.ACTIVE)
        self.assertEqual(testing_future.status, Testing.Status.SCHEDULED)

        # Проверяем, что была вызвана фоновая рассылка email через Celery
        mock_batch_delay.assert_called_once_with(testing_due.id)

    @patch("testing_app.services.event_service.auto_activate_scheduled_testings")
    def test_auto_activate_scheduled_testings_task(self, mock_service_func) -> None:
        """Проверяет запуск Celery-таска auto_activate_scheduled_testings_task."""
        mock_service_func.return_value = {
            "processed_count": 1,
            "activated_count": 1,
            "activated_ids": [10],
            "errors": [],
        }

        result = auto_activate_scheduled_testings_task.apply().get()
        self.assertEqual(result["activated_count"], 1)
        mock_service_func.assert_called_once()
