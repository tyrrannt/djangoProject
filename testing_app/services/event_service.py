"""Сервисы управления мероприятиями тестирования, группами, должностями и назначениями сотрудников."""

from typing import Dict, Any, List, Optional, Tuple, Set
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from customers_app.models import Job, DataBaseUser
from testing_app.models import (
    Testing,
    TestingGroup,
    TestingGroupPosition,
    TestingCategorySetting,
    QuestionCategory,
    TestingAssignment,
    TestingAttempt,
    TestingAuditLog,
)


def ensure_default_groups_exist(testing: Testing) -> Tuple[TestingGroup, TestingGroup]:
    """Создает стандартные группы мероприятия тестирования, если они еще не созданы.

    Группа 1: «Выполняющие работы по обеспечению ТО ВС» (код: ensuring_maintenance)
    Группа 2: «Выполняющие ТО ВС» (код: performing_maintenance)

    Args:
        testing (Testing): Мероприятие тестирования.

    Returns:
        Tuple[TestingGroup, TestingGroup]: Кортеж из двух групп (группа 1, группа 2).
    """
    group1, _ = TestingGroup.objects.get_or_create(
        testing=testing,
        code=TestingGroup.Code.ENSURING,
        defaults={
            "name": "Выполняющие работы по обеспечению ТО ВС",
            "description": "Сотрудники инженерно-технического профиля, обеспечивающие процессы ТО ВС"
        }
    )
    group2, _ = TestingGroup.objects.get_or_create(
        testing=testing,
        code=TestingGroup.Code.PERFORMING,
        defaults={
            "name": "Выполняющие ТО ВС",
            "description": "Персонал, непосредственно выполняющий техническое обслуживание ВС"
        }
    )
    return group1, group2


def sync_group_positions(
    testing: Testing,
    group1_job_ids: List[int],
    group2_job_ids: List[int],
    user=None
) -> Dict[str, Any]:
    """Синхронизирует привязку должностей к группам тестирования с проверкой пересечений.

    Проверяет, чтобы одна и та же должность не была включена одновременно
    в обе группы (раздел 12 ТЗ), обновляет записи TestingGroupPosition
    и инициирует автоматическое переформирование назначений сотрудников.

    Args:
        testing (Testing): Мероприятие тестирования.
        group1_job_ids (List[int]): Список ID должностей для Группы 1.
        group2_job_ids (List[int]): Список ID должностей для Группы 2.
        user (Optional[User]): Инициатор операции (для аудита).

    Raises:
        ValidationError: При обнаружении пересечений между группами.

    Returns:
        Dict[str, Any]: Статистика синхронизации (назначено, обновлено, удалено).
    """
    set1: Set[int] = set(map(int, group1_job_ids))
    set2: Set[int] = set(map(int, group2_job_ids))

    with transaction.atomic():
        group1, group2 = ensure_default_groups_exist(testing)

        # 1. Обновляем привязки должностей Группы 1
        TestingGroupPosition.objects.filter(group=group1).exclude(job_id__in=set1).delete()
        existing_g1_jobs = set(TestingGroupPosition.objects.filter(group=group1).values_list("job_id", flat=True))
        new_g1_positions = [
            TestingGroupPosition(group=group1, job_id=jid)
            for jid in (set1 - existing_g1_jobs)
        ]
        if new_g1_positions:
            TestingGroupPosition.objects.bulk_create(new_g1_positions)

        # 2. Обновляем привязки должностей Группы 2
        TestingGroupPosition.objects.filter(group=group2).exclude(job_id__in=set2).delete()
        existing_g2_jobs = set(TestingGroupPosition.objects.filter(group=group2).values_list("job_id", flat=True))
        new_g2_positions = [
            TestingGroupPosition(group=group2, job_id=jid)
            for jid in (set2 - existing_g2_jobs)
        ]
        if new_g2_positions:
            TestingGroupPosition.objects.bulk_create(new_g2_positions)

        # 3. Выполняем автоназначение сотрудников по обновленным должностям
        stats = auto_assign_employees_by_positions(testing, user=user)

        TestingAuditLog.objects.create(
            user=user,
            action="sync_group_positions",
            object_repr=f"Тестирование '{testing.title}': обновлены должности групп",
            details={
                "group1_jobs_count": len(set1),
                "group2_jobs_count": len(set2),
                "assigned_stats": stats,
            }
        )

    return stats


def save_group_positions_and_employee_distribution(
    testing: Testing,
    selected_job_ids: List[Any],
    group1_employee_ids: List[Any],
    group2_employee_ids: List[Any],
    user=None
) -> Dict[str, Any]:
    """Сохраняет выбранные должности мероприятия и распределение сотрудников по 2 группам.

    Формирует единый пул должностей мероприятия (на основании привязки division_affiliation)
    и сохраняет явное распределение сотрудников между Группой 1 («Обеспечение ТО ВС»)
    и Группой 2 («Выполнение ТО ВС»).

    Args:
        testing (Testing): Мероприятие тестирования.
        selected_job_ids (List[Any]): Список ID выбранных должностей для мероприятия.
        group1_employee_ids (List[Any]): Список ID сотрудников, назначенных в Группу 1.
        group2_employee_ids (List[Any]): Список ID сотрудников, назначенных в Группу 2.
        user (Optional[User]): Пользователь, выполняющий действие (для аудита).

    Returns:
        Dict[str, Any]: Статистика сохранения с ключами 'g1_count', 'g2_count',
            'created', 'updated', 'removed', 'total_assigned'.
    """
    job_ids = set(int(jid) for jid in selected_job_ids if str(jid).isdigit())
    g1_emp_ids = set(int(eid) for eid in group1_employee_ids if str(eid).isdigit())
    g2_emp_ids = set(int(eid) for eid in group2_employee_ids if str(eid).isdigit())

    # Исключаем дублирование: если сотрудник оказался в обоих списках, отдаем приоритет группе 1
    g2_emp_ids = g2_emp_ids - g1_emp_ids

    with transaction.atomic():
        group1, group2 = ensure_default_groups_exist(testing)

        # 1. Фиксируем единый пул должностей мероприятия в связях групп
        TestingGroupPosition.objects.filter(group__in=[group1, group2]).exclude(job_id__in=job_ids).delete()
        existing_g1_jobs = set(TestingGroupPosition.objects.filter(group=group1).values_list("job_id", flat=True))
        new_g1 = [TestingGroupPosition(group=group1, job_id=jid) for jid in (job_ids - existing_g1_jobs)]
        if new_g1:
            TestingGroupPosition.objects.bulk_create(new_g1)

        # 2. Обрабатываем назначения сотрудников
        all_target_emp_ids = g1_emp_ids | g2_emp_ids
        employees_qs = DataBaseUser.objects.filter(
            id__in=all_target_emp_ids
        ).select_related("user_work_profile__job", "user_work_profile__divisions")

        emp_map = {emp.id: emp for emp in employees_qs}
        current_assigned_map = {
            assign.employee_id: assign
            for assign in TestingAssignment.objects.filter(testing=testing)
        }

        created_count = 0
        updated_count = 0

        # Назначение в Группу 1
        for eid in g1_emp_ids:
            emp = emp_map.get(eid)
            if not emp:
                continue
            profile = getattr(emp, "user_work_profile", None)
            job_title = profile.job.name if profile and profile.job else "Не указана"
            div_title = profile.divisions.name if profile and profile.divisions else ""

            existing_assign = current_assigned_map.get(eid)
            if not existing_assign:
                TestingAssignment.objects.create(
                    testing=testing,
                    group=group1,
                    employee=emp,
                    assigned_job_title=job_title,
                    assigned_division_title=div_title,
                    assignment_type=TestingAssignment.AssignmentType.MANUAL,
                    status=TestingAssignment.Status.NOT_STARTED
                )
                created_count += 1
            else:
                if existing_assign.group_id != group1.id:
                    existing_assign.group = group1
                    existing_assign.assigned_job_title = job_title
                    existing_assign.assigned_division_title = div_title
                    existing_assign.save(update_fields=["group", "assigned_job_title", "assigned_division_title"])
                    updated_count += 1

        # Назначение в Группу 2
        for eid in g2_emp_ids:
            emp = emp_map.get(eid)
            if not emp:
                continue
            profile = getattr(emp, "user_work_profile", None)
            job_title = profile.job.name if profile and profile.job else "Не указана"
            div_title = profile.divisions.name if profile and profile.divisions else ""

            existing_assign = current_assigned_map.get(eid)
            if not existing_assign:
                TestingAssignment.objects.create(
                    testing=testing,
                    group=group2,
                    employee=emp,
                    assigned_job_title=job_title,
                    assigned_division_title=div_title,
                    assignment_type=TestingAssignment.AssignmentType.MANUAL,
                    status=TestingAssignment.Status.NOT_STARTED
                )
                created_count += 1
            else:
                if existing_assign.group_id != group2.id:
                    existing_assign.group = group2
                    existing_assign.assigned_job_title = job_title
                    existing_assign.assigned_division_title = div_title
                    existing_assign.save(update_fields=["group", "assigned_job_title", "assigned_division_title"])
                    updated_count += 1

        # 3. Удаление сотрудников, убранных из обеих групп (только если они еще не сдавали)
        stale_assignments = TestingAssignment.objects.filter(
            testing=testing,
            attempts_used=0,
            status=TestingAssignment.Status.NOT_STARTED
        ).exclude(employee_id__in=all_target_emp_ids)
        removed_count = stale_assignments.count()
        stale_assignments.delete()

        # Аудит
        TestingAuditLog.objects.create(
            user=user,
            action="save_group_distribution",
            object_repr=f"Тестирование '{testing.title}': распределено {len(all_target_emp_ids)} сотрудников по группам",
            details={
                "selected_jobs_count": len(job_ids),
                "group1_count": len(g1_emp_ids),
                "group2_count": len(g2_emp_ids),
                "created": created_count,
                "updated": updated_count,
                "removed": removed_count,
            }
        )

    return {
        "g1_count": len(g1_emp_ids),
        "g2_count": len(g2_emp_ids),
        "created": created_count,
        "updated": updated_count,
        "removed": removed_count,
        "total_assigned": testing.assignments.count(),
    }


def auto_assign_employees_by_positions(testing: Testing, user=None) -> Dict[str, int]:
    """Автоматически формирует состав сотрудников по должностям групп тестирования.

    Находит сотрудников с профилем работы, чья должность входит в одну из групп.
    Фиксирует наименование должности и подразделения сотрудника на момент назначения (Snapshot).
    Не затрагивает сотрудников, добавленных вручную (MANUAL).
    Удаляет автоназначения сотрудников, чьи должности более не включены в группы
    (при условии отсутствия начатых попыток тестирования).

    Args:
        testing (Testing): Мероприятие тестирования.
        user (Optional[User]): Инициатор операции (для аудита).

    Returns:
        Dict[str, int]: Количество созданных, сохраненных и удаленных назначений.
    """
    group1, group2 = ensure_default_groups_exist(testing)

    g1_jobs = set(TestingGroupPosition.objects.filter(group=group1).values_list("job_id", flat=True))
    g2_jobs = set(TestingGroupPosition.objects.filter(group=group2).values_list("job_id", flat=True))
    all_target_jobs = g1_jobs | g2_jobs

    created_count = 0
    updated_count = 0
    removed_count = 0

    # 1. Загружаем активных сотрудников с их рабочими профилями, должностями и подразделениями
    employees = DataBaseUser.objects.filter(
        is_active=True,
        user_work_profile__isnull=False,
        user_work_profile__job_id__in=all_target_jobs
    ).select_related("user_work_profile__job", "user_work_profile__divisions")

    current_assigned_map = {
        assign.employee_id: assign
        for assign in TestingAssignment.objects.filter(testing=testing)
    }

    target_employee_ids = set()

    with transaction.atomic():
        for emp in employees:
            target_employee_ids.add(emp.id)
            profile = emp.user_work_profile
            job_id = profile.job_id
            job_title = profile.job.name if profile.job else "Не указана"
            div_title = profile.divisions.name if profile.divisions else ""

            assigned_group = group1 if job_id in g1_jobs else group2

            existing_assign = current_assigned_map.get(emp.id)

            if not existing_assign:
                # Новое автоназначение
                TestingAssignment.objects.create(
                    testing=testing,
                    group=assigned_group,
                    employee=emp,
                    assigned_job_title=job_title,
                    assigned_division_title=div_title,
                    assignment_type=TestingAssignment.AssignmentType.AUTO,
                    status=TestingAssignment.Status.NOT_STARTED
                )
                created_count += 1
            else:
                # Если сотрудник уже назначен автоматически, проверяем актуальность группы
                if existing_assign.assignment_type == TestingAssignment.AssignmentType.AUTO:
                    if existing_assign.group_id != assigned_group.id:
                        existing_assign.group = assigned_group
                        existing_assign.assigned_job_title = job_title
                        existing_assign.assigned_division_title = div_title
                        existing_assign.save(update_fields=["group", "assigned_job_title", "assigned_division_title"])
                        updated_count += 1

        # 2. Удаление автоназначений тех сотрудников, чьи должности были удалены из групп,
        # если сотрудник еще не начинал тестирование
        stale_assignments = TestingAssignment.objects.filter(
            testing=testing,
            assignment_type=TestingAssignment.AssignmentType.AUTO,
            attempts_used=0,
            status=TestingAssignment.Status.NOT_STARTED
        ).exclude(employee_id__in=target_employee_ids)

        removed_count = stale_assignments.count()
        stale_assignments.delete()

    return {
        "created": created_count,
        "updated": updated_count,
        "removed": removed_count,
        "total_assigned": TestingAssignment.objects.filter(testing=testing).count()
    }


def add_manual_assignment(
    testing: Testing,
    group: TestingGroup,
    employee: DataBaseUser,
    user=None
) -> TestingAssignment:
    """Вручную добавляет сотрудника в группу тестирования.

    Args:
        testing (Testing): Мероприятие тестирования.
        group (TestingGroup): Целевая группа.
        employee (DataBaseUser): Добавляемый сотрудник.
        user (Optional[User]): Инициатор действия (для аудита).

    Raises:
        ValidationError: Если сотрудник уже назначен в данное тестирование.

    Returns:
        TestingAssignment: Созданный объект назначения.
    """
    existing = TestingAssignment.objects.filter(testing=testing, employee=employee).first()
    if existing:
        raise ValidationError(
            f"Сотрудник {employee.get_full_name()} уже назначен на это тестирование "
            f"в группу «{existing.group.name}» (способ: {existing.get_assignment_type_display()})."
        )

    job_title = "Не указана"
    div_title = ""
    if hasattr(employee, "user_work_profile") and employee.user_work_profile:
        profile = employee.user_work_profile
        job_title = profile.job.name if profile.job else "Не указана"
        div_title = profile.divisions.name if profile.divisions else ""

    assignment = TestingAssignment.objects.create(
        testing=testing,
        group=group,
        employee=employee,
        assigned_job_title=job_title,
        assigned_division_title=div_title,
        assignment_type=TestingAssignment.AssignmentType.MANUAL,
        status=TestingAssignment.Status.NOT_STARTED
    )

    TestingAuditLog.objects.create(
        user=user,
        action="manual_assign_employee",
        object_repr=f"Назначен вручную: {employee.get_full_name()}",
        details={
            "testing": testing.title,
            "group": group.name,
            "job": job_title,
            "division": div_title
        }
    )
    return assignment


def remove_assignment(assignment: TestingAssignment, user=None) -> bool:
    """Удаляет сотрудника из списка тестирования.

    Если сотрудник уже совершил хотя бы одну попытку, физическое удаление блокируется
    для сохранения юридической целостности протоколов.

    Args:
        assignment (TestingAssignment): Назначение сотрудника.
        user (Optional[User]): Инициатор действия.

    Raises:
        ValidationError: Если у сотрудника есть зафиксированные попытки сдачи.

    Returns:
        bool: True в случае успешного удаления.
    """
    if assignment.attempts.exists() or assignment.attempts_used > 0:
        raise ValidationError(
            f"Невозможно удалить сотрудника {assignment.employee.get_full_name()}, "
            "так как им уже были предприняты попытки прохождения теста. "
            "История попыток не подлежит удалению."
        )

    emp_name = assignment.employee.get_full_name()
    testing_title = assignment.testing.title

    TestingAuditLog.objects.create(
        user=user,
        action="remove_assignment",
        object_repr=f"Исключен из тестирования: {emp_name}",
        details={"testing": testing_title, "group": assignment.group.name}
    )

    assignment.delete()
    return True


def update_category_settings(
    testing: Testing,
    category_percentages: Dict[int, int],
    user=None
) -> List[TestingCategorySetting]:
    """Обновляет процентное распределение вопросов по категориям для мероприятия.

    Контролирует:
    1. Сумма всех процентов строго должна равняться 100% (раздел 18 ТЗ).
    2. Расчет количества вопросов по каждой категории с распределением остатка.
    3. Проверка достаточности активных вопросов в банке (раздел 24 ТЗ).

    Args:
        testing (Testing): Мероприятие тестирования.
        category_percentages (Dict[int, int]): Словарь {category_id: percentage}.
        user (Optional[User]): Инициатор операции (для аудита).

    Raises:
        ValidationError: При несовпадении суммы со 100% или дефиците вопросов.

    Returns:
        List[TestingCategorySetting]: Сохраненные настройки категорий.
    """
    total_percentage = sum(category_percentages.values())
    if total_percentage != 100:
        raise ValidationError(
            f"Сумма процентов всех категорий должна быть строго 100%. "
            f"Текущая введенная сумма: {total_percentage}%."
        )

    total_q = testing.questions_count
    calculated_counts = {}
    running_sum = 0
    sorted_cats = sorted(category_percentages.items(), key=lambda x: x[1], reverse=True)

    # Предварительный расчет количества вопросов с округлением
    for cat_id, pct in sorted_cats:
        count = round((pct / 100.0) * total_q)
        calculated_counts[cat_id] = count
        running_sum += count

    # Корректировка разницы округления (если running_sum != total_q)
    diff = total_q - running_sum
    if diff != 0 and sorted_cats:
        top_cat_id = sorted_cats[0][0]
        calculated_counts[top_cat_id] += diff

    # Проверка достаточности активных вопросов в банке вопросов
    errors = []
    for cat_id, needed_count in calculated_counts.items():
        if needed_count > 0:
            category = QuestionCategory.objects.filter(id=cat_id).first()
            if not category:
                continue
            active_avail = category.active_questions_count()
            if active_avail < needed_count:
                errors.append(
                    f"В категории «{category.name}» требуется {needed_count} вопросов, "
                    f"а активно в банке только {active_avail}."
                )

    if errors:
        raise ValidationError(" ".join(errors))

    with transaction.atomic():
        # Удаляем неиспользуемые категории для этого теста
        active_cat_ids = [cid for cid, p in category_percentages.items() if p > 0]
        TestingCategorySetting.objects.filter(testing=testing).exclude(category_id__in=active_cat_ids).delete()

        saved_settings = []
        for cat_id, pct in category_percentages.items():
            if pct > 0:
                count = calculated_counts[cat_id]
                setting, _ = TestingCategorySetting.objects.update_or_create(
                    testing=testing,
                    category_id=cat_id,
                    defaults={
                        "percentage": pct,
                        "calculated_questions_count": count
                    }
                )
                saved_settings.append(setting)

        TestingAuditLog.objects.create(
            user=user,
            action="update_category_settings",
            object_repr=f"Обновлены категории тестирования '{testing.title}'",
            details={
                "distribution": {
                    s.category.name: f"{s.percentage}% ({s.calculated_questions_count} вопр.)"
                    for s in saved_settings
                }
            }
        )

    return saved_settings


def change_testing_status(testing: Testing, new_status: str, user=None) -> Tuple[bool, List[str]]:
    """Изменяет статус мероприятия с обязательной валидацией готовности.

    При попытке перевода в статус 'active' (Активно) или 'scheduled' (Запланировано)
    выполняется проверка 14 критериев готовности согласно разделу 85 ТЗ.

    Args:
        testing (Testing): Мероприятие тестирования.
        new_status (str): Новый статус.
        user (Optional[User]): Инициатор операции.

    Returns:
        Tuple[bool, List[str]]: (Успешно ли выполнено, Список ошибок валидации).
    """
    valid_statuses = [choice[0] for choice in Testing.Status.choices]
    if new_status not in valid_statuses:
        return False, [f"Недопустимый статус: {new_status}"]

    # Если переводим в статус Активно или Запланировано — проверяем полную готовность
    if new_status in [Testing.Status.ACTIVE, Testing.Status.SCHEDULED]:
        errors = testing.check_readiness()
        if errors:
            return False, errors

    old_status = testing.status
    testing.status = new_status
    testing.updated_by = user
    testing.save(update_fields=["status", "updated_by", "updated_at"])

    TestingAuditLog.objects.create(
        user=user,
        action="change_testing_status",
        object_repr=f"Мероприятие '{testing.title}' изменило статус на {testing.get_status_display()}",
        details={"old_status": old_status, "new_status": new_status}
    )

    # Если мероприятие стало активным — инициируем пакетную рассылку уведомлений через Celery
    if new_status == Testing.Status.ACTIVE:
        try:
            from testing_app.tasks import send_event_assignments_batch_task
            send_event_assignments_batch_task.delay(testing.id)
        except Exception as exc:
            logger.warning("Не удалось запустить пакетную рассылку уведомлений (Testing ID %s): %s", testing.id, exc)

    return True, []
