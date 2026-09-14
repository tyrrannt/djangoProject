# Generated for Company Organizational Structure & Division Hierarchy

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers_app", "0084_rename_customers_a_thumbpr_6f8092_idx_customers_a_thumbpr_3a89e2_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrgStructure",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        default="Общая структурная схема ООО Авиакомпания «БАРКОЛ»",
                        max_length=255,
                        verbose_name="Наименование структуры",
                    ),
                ),
                (
                    "version_code",
                    models.CharField(
                        blank=True,
                        default="2026-09",
                        max_length=50,
                        verbose_name="Код версии",
                    ),
                ),
                (
                    "start_date",
                    models.DateField(
                        default=django.utils.timezone.now,
                        verbose_name="Дата ввода в действие",
                    ),
                ),
                (
                    "end_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Дата окончания действия",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        verbose_name="Актуальная действующая структура",
                    ),
                ),
                (
                    "approved_by",
                    models.CharField(
                        blank=True,
                        default="Генеральный директор В.С. Бархотов",
                        max_length=255,
                        verbose_name="Кем утверждено",
                    ),
                ),
                (
                    "approval_date",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Дата утверждения",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Описание / основание",
                    ),
                ),
                (
                    "raw_layout_json",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Разметка холста конструктора (JSON)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Дата создания",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Дата обновления",
                    ),
                ),
            ],
            options={
                "verbose_name": "Организационная структура",
                "verbose_name_plural": "Организационные структуры",
                "ordering": ["-start_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OrgStructureNode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "custom_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Наименование блока",
                    ),
                ),
                (
                    "node_type",
                    models.CharField(
                        choices=[
                            ("TOP_MANAGEMENT", "Высшее руководство"),
                            ("SERVICE", "Служба"),
                            ("DETACHMENT", "Летный отряд"),
                            ("DIVISION", "Отдел / Подразделение"),
                            ("GROUP", "Группа / Участок / Сектор"),
                            ("SUBDIVISION", "Обособленное подразделение (ОП МПД)"),
                            ("ADVISORY", "Совещательный орган / Совет"),
                            ("ASSISTANT", "Аппарат руководства / Секретариат"),
                        ],
                        default="DIVISION",
                        max_length=30,
                        verbose_name="Тип узла",
                    ),
                ),
                (
                    "level",
                    models.PositiveIntegerField(
                        default=1,
                        verbose_name="Уровень иерархии",
                    ),
                ),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Порядок сортировки",
                    ),
                ),
                (
                    "pos_x",
                    models.IntegerField(
                        default=100,
                        verbose_name="Координата X на холсте",
                    ),
                ),
                (
                    "pos_y",
                    models.IntegerField(
                        default=100,
                        verbose_name="Координата Y на холсте",
                    ),
                ),
                (
                    "color_scheme",
                    models.CharField(
                        blank=True,
                        default="blue",
                        max_length=30,
                        verbose_name="Цветовая тема",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        verbose_name="Активен",
                    ),
                ),
                (
                    "division",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="org_nodes",
                        to="customers_app.division",
                        verbose_name="Подразделение",
                    ),
                ),
                (
                    "head_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="org_head_nodes",
                        to="customers_app.job",
                        verbose_name="Руководящая должность",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="customers_app.orgstructurenode",
                        verbose_name="Вышестоящее звено (Родитель)",
                    ),
                ),
                (
                    "structure",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nodes",
                        to="customers_app.orgstructure",
                        verbose_name="Схема оргструктуры",
                    ),
                ),
            ],
            options={
                "verbose_name": "Узел оргструктуры",
                "verbose_name_plural": "Узлы оргструктуры",
                "ordering": ["level", "order", "id"],
            },
        ),
        migrations.CreateModel(
            name="OrgNodeLeadershipHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date_from",
                    models.DateField(
                        default=django.utils.timezone.now,
                        verbose_name="Дата начала руководства",
                    ),
                ),
                (
                    "date_to",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Дата окончания руководства",
                    ),
                ),
                (
                    "is_current",
                    models.BooleanField(
                        default=True,
                        verbose_name="Действующий руководитель",
                    ),
                ),
                (
                    "order_number",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=150,
                        verbose_name="Приказ / основание",
                    ),
                ),
                (
                    "comment",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="Примечание",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Дата фиксации записи",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leadership_records",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Руководитель (Сотрудник)",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="leadership_records",
                        to="customers_app.job",
                        verbose_name="Должность руководителя",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leadership_history",
                        to="customers_app.orgstructurenode",
                        verbose_name="Узел оргструктуры",
                    ),
                ),
            ],
            options={
                "verbose_name": "История руководства узла",
                "verbose_name_plural": "История руководства узлов",
                "ordering": ["-is_current", "-date_from", "-created_at"],
            },
        ),
    ]
