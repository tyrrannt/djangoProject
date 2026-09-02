# Generated for testing_app

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("customers_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestionCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True, verbose_name="Название категории")),
                ("description", models.TextField(blank=True, default="", verbose_name="Описание")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Активна")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
            ],
            options={
                "verbose_name": "Категория вопросов",
                "verbose_name_plural": "Категории вопросов",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(verbose_name="Текст вопроса")),
                ("explanation", models.TextField(blank=True, default="", verbose_name="Пояснение правильного ответа")),
                ("status", models.CharField(choices=[("active", "Активный"), ("archived", "Архивный")], db_index=True, default="active", max_length=20, verbose_name="Статус")),
                ("difficulty", models.CharField(choices=[("easy", "Низкая"), ("medium", "Средняя"), ("hard", "Повышенная"), ("very_hard", "Высокая")], default="medium", max_length=20, verbose_name="Уровень сложности")),
                ("times_used", models.PositiveIntegerField(default=0, verbose_name="Количество использований")),
                ("times_correct", models.PositiveIntegerField(default=0, verbose_name="Правильных ответов")),
                ("times_incorrect", models.PositiveIntegerField(default=0, verbose_name="Неправильных ответов")),
                ("last_used_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата последнего использования")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата изменения")),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_questions", to=settings.AUTH_USER_MODEL, verbose_name="Автор вопроса")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="testing_app.questioncategory", verbose_name="Категория")),
            ],
            options={
                "verbose_name": "Вопрос",
                "verbose_name_plural": "Банк вопросов",
                "ordering": ["category", "id"],
            },
        ),
        migrations.CreateModel(
            name="AnswerOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(verbose_name="Текст варианта ответа")),
                ("order_num", models.PositiveSmallIntegerField(default=1, verbose_name="Порядковый номер")),
                ("is_correct", models.BooleanField(db_index=True, default=False, verbose_name="Правильный ответ")),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="testing_app.question", verbose_name="Вопрос")),
            ],
            options={
                "verbose_name": "Вариант ответа",
                "verbose_name_plural": "Варианты ответов",
                "ordering": ["order_num"],
            },
        ),
        migrations.CreateModel(
            name="Testing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Наименование тестирования")),
                ("order_number", models.CharField(max_length=100, verbose_name="Номер приказа")),
                ("order_date", models.DateField(verbose_name="Дата приказа")),
                ("order_name", models.CharField(blank=True, default="", max_length=255, verbose_name="Наименование приказа")),
                ("description", models.TextField(blank=True, default="", verbose_name="Описание мероприятия")),
                ("start_datetime", models.DateTimeField(verbose_name="Дата и время начала")),
                ("end_datetime", models.DateTimeField(verbose_name="Дата и время окончания")),
                ("questions_count", models.PositiveIntegerField(default=20, verbose_name="Количество вопросов")),
                ("passing_score_percentage", models.PositiveIntegerField(default=80, verbose_name="Проходной процент (%)")),
                ("max_attempts", models.PositiveIntegerField(default=5, verbose_name="Максимум попыток")),
                ("attempt_duration_minutes", models.PositiveIntegerField(default=60, verbose_name="Продолжительность попытки (мин)")),
                ("status", models.CharField(choices=[("draft", "Черновик"), ("preparing", "Подготовка"), ("scheduled", "Запланировано"), ("active", "Активно"), ("completed", "Завершено"), ("archived", "Архив")], db_index=True, default="draft", max_length=20, verbose_name="Статус мероприятия")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата изменения")),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_testings", to=settings.AUTH_USER_MODEL, verbose_name="Автор")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_testings", to=settings.AUTH_USER_MODEL, verbose_name="Автор последнего изменения")),
            ],
            options={
                "verbose_name": "Мероприятие тестирования",
                "verbose_name_plural": "Мероприятия тестирования",
                "ordering": ["-start_datetime"],
            },
        ),
        migrations.CreateModel(
            name="TestingGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Наименование группы")),
                ("code", models.CharField(choices=[("ensuring_maintenance", "Обеспечение ТО ВС"), ("performing_maintenance", "Выполнение ТО ВС"), ("other", "Другая")], default="performing_maintenance", max_length=50, verbose_name="Код группы")),
                ("description", models.TextField(blank=True, default="", verbose_name="Описание группы")),
                ("testing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="groups", to="testing_app.testing", verbose_name="Мероприятие тестирования")),
            ],
            options={
                "verbose_name": "Группа тестирования",
                "verbose_name_plural": "Группы тестирования",
                "unique_together": {("testing", "name")},
            },
        ),
        migrations.CreateModel(
            name="TestingGroupPosition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="group_positions", to="testing_app.testinggroup", verbose_name="Группа тестирования")),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="testing_group_positions", to="customers_app.job", verbose_name="Должность")),
            ],
            options={
                "verbose_name": "Должность группы тестирования",
                "verbose_name_plural": "Должности групп тестирования",
                "unique_together": {("group", "job")},
            },
        ),
        migrations.CreateModel(
            name="TestingCategorySetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("percentage", models.PositiveIntegerField(verbose_name="Процент участия (%)")),
                ("calculated_questions_count", models.PositiveIntegerField(default=0, verbose_name="Рассчитанное количество вопросов")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="testing_settings", to="testing_app.questioncategory", verbose_name="Категория вопросов")),
                ("testing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="category_settings", to="testing_app.testing", verbose_name="Мероприятие")),
            ],
            options={
                "verbose_name": "Настройка категории для тестирования",
                "verbose_name_plural": "Настройки категорий для тестирования",
                "unique_together": {("testing", "category")},
            },
        ),
        migrations.CreateModel(
            name="TestingAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_job_title", models.CharField(max_length=255, verbose_name="Должность на момент назначения")),
                ("assigned_division_title", models.CharField(blank=True, default="", max_length=255, verbose_name="Подразделение на момент назначения")),
                ("assignment_type", models.CharField(choices=[("auto_by_position", "Автоматически по должности"), ("manual", "Добавлен вручную")], default="auto_by_position", max_length=20, verbose_name="Способ назначения")),
                ("status", models.CharField(choices=[("not_started", "Не начато"), ("in_progress", "В процессе"), ("passed", "Пройдено"), ("failed", "Не пройдено"), ("attempts_exhausted", "Попытки исчерпаны"), ("on_control", "Направлен на контроль"), ("period_expired", "Период завершен"), ("overdue", "Не завершено в установленный срок")], db_index=True, default="not_started", max_length=30, verbose_name="Статус тестирования")),
                ("is_on_control", models.BooleanField(db_index=True, default=False, verbose_name="Направлен на контроль")),
                ("attempts_used", models.PositiveIntegerField(default=0, verbose_name="Использовано попыток")),
                ("best_score", models.FloatField(blank=True, null=True, verbose_name="Лучший результат (%)")),
                ("last_score", models.FloatField(blank=True, null=True, verbose_name="Последний результат (%)")),
                ("assigned_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата назначения")),
                ("passed_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата успешной сдачи")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="testing_assignments", to=settings.AUTH_USER_MODEL, verbose_name="Сотрудник")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignments", to="testing_app.testinggroup", verbose_name="Группа")),
                ("testing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignments", to="testing_app.testing", verbose_name="Мероприятие")),
            ],
            options={
                "verbose_name": "Назначение сотрудника на тестирование",
                "verbose_name_plural": "Назначения сотрудников",
                "ordering": ["assigned_division_title", "assigned_job_title", "employee__last_name"],
                "unique_together": {("testing", "employee")},
            },
        ),
        migrations.CreateModel(
            name="TestingAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attempt_number", models.PositiveIntegerField(default=1, verbose_name="Номер попытки")),
                ("started_at", models.DateTimeField(auto_now_add=True, verbose_name="Время начала")),
                ("planned_end_at", models.DateTimeField(verbose_name="Плановое время окончания (таймер)")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="Время завершения")),
                ("duration_seconds", models.PositiveIntegerField(default=0, verbose_name="Продолжительность (сек)")),
                ("status", models.CharField(choices=[("in_progress", "В процессе"), ("completed", "Завершена"), ("expired", "Время истекло"), ("cancelled", "Отменена")], db_index=True, default="in_progress", max_length=20, verbose_name="Статус попытки")),
                ("total_questions", models.PositiveIntegerField(default=0, verbose_name="Всего вопросов")),
                ("correct_answers", models.PositiveIntegerField(default=0, verbose_name="Правильных ответов")),
                ("score_percentage", models.FloatField(default=0.0, verbose_name="Результат (%)")),
                ("is_passed", models.BooleanField(db_index=True, default=False, verbose_name="Тест пройден успешно")),
                ("completion_reason", models.CharField(choices=[("user_completed", "Завершено пользователем"), ("time_expired", "Время попытки истекло"), ("period_expired", "Период тестирования завершен"), ("admin_terminated", "Административное завершение")], default="user_completed", max_length=30, verbose_name="Причина завершения")),
                ("certificate_uuid", models.UUIDField(db_index=True, default=uuid.uuid4, unique=True, verbose_name="Уникальный UUID сертификата")),
                ("result_number", models.CharField(blank=True, db_index=True, default="", max_length=50, verbose_name="Номер результата (TEST-YYYY-XXXX)")),
                ("qr_code_image", models.ImageField(blank=True, null=True, upload_to="testing_qr_codes/", verbose_name="QR-код проверки")),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="testing_app.testingassignment", verbose_name="Назначение сотрудника")),
            ],
            options={
                "verbose_name": "Попытка тестирования",
                "verbose_name_plural": "Попытки тестирования",
                "ordering": ["-started_at"],
                "unique_together": {("assignment", "attempt_number")},
            },
        ),
        migrations.CreateModel(
            name="AttemptQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category_name", models.CharField(max_length=255, verbose_name="Категория вопроса (снимок)")),
                ("order_num", models.PositiveIntegerField(verbose_name="Порядковый номер")),
                ("question_text", models.TextField(verbose_name="Текст вопроса (снимок)")),
                ("options_snapshot", models.JSONField(default=list, verbose_name="Снимок вариантов ответов")),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="testing_app.testingattempt", verbose_name="Попытка")),
                ("source_question", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attempt_questions", to="testing_app.question", verbose_name="Исходный вопрос")),
            ],
            options={
                "verbose_name": "Вопрос попытки (снимок)",
                "verbose_name_plural": "Вопросы попытки (снимки)",
                "ordering": ["order_num"],
                "unique_together": {("attempt", "order_num")},
            },
        ),
        migrations.CreateModel(
            name="UserAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selected_option_id", models.IntegerField(blank=True, null=True, verbose_name="Выбранный вариант ID")),
                ("is_correct", models.BooleanField(default=False, verbose_name="Ответ правильный")),
                ("first_viewed_at", models.DateTimeField(auto_now_add=True, verbose_name="Время первого просмотра")),
                ("answered_at", models.DateTimeField(blank=True, null=True, verbose_name="Время ответа")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Время изменения")),
                ("seconds_spent", models.PositiveIntegerField(default=0, verbose_name="Затрачено секунд")),
                ("attempt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="testing_app.testingattempt", verbose_name="Попытка")),
                ("attempt_question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="user_answers", to="testing_app.attemptquestion", verbose_name="Вопрос попытки")),
            ],
            options={
                "verbose_name": "Ответ сотрудника",
                "verbose_name_plural": "Ответы сотрудников",
                "unique_together": {("attempt", "attempt_question")},
            },
        ),
        migrations.CreateModel(
            name="TestingAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(db_index=True, max_length=100, verbose_name="Действие")),
                ("object_repr", models.CharField(max_length=255, verbose_name="Объект")),
                ("details", models.JSONField(default=dict, verbose_name="Детали изменения")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP-адрес")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата и время")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Запись аудита тестирования",
                "verbose_name_plural": "Журнал аудита тестирования",
                "ordering": ["-created_at"],
            },
        ),
    ]
