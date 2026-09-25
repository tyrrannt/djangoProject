"""Сервисный слой управления правами доступа и ролями пользователей портала.

Обеспечивает трехуровневую модель прав:
1. Должностные группы (Job-based) — наследуются из штатной должности (Job.group);
2. Персональные группы (Personal groups) — дополнительные права конкретного сотрудника (personal_groups);
3. Защищенные доменные роли (Protected Domain Roles) — роли ЛПК ([ЛПК] *), почты, тестирования,
   обладающие полным иммунитетом от автоматического сброса.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from django.contrib.auth.models import Group
from django.db import transaction

from customers_app.models import DataBaseUser, Groups

logger = logging.getLogger(__name__)

# Префиксы наименований защищенных доменных ролей подсистем
PROTECTED_ROLE_PREFIXES: Tuple[str, ...] = (
    "[ЛПК]",  # Роли Летно-производственного комплекса
)

# Точные наименования защищенных групп (подсистемы, сервисы, исторические алиасы)
PROTECTED_ROLE_NAMES: Set[str] = {
    # Роли Летно-производственного комплекса
    "[ЛПК] Руководство",
    "[ЛПК] Диспетчеры планирования",
    "[ЛПК] Инженерная служба (ИАС)",
    "[ЛПК] Летная служба",
    "[ЛПК] Кадры и охрана труда",
    "[ЛПК] Летный состав",
    "Планирование полетов",
    "Руководство полетов",
    "Летный состав",
    # Специальные модульные роли
    "Администраторы почты",
    "Ответственные за тестирование",
}


class UserAccessService:
    """Сервис трехуровневой синхронизации и аудита прав доступа пользователей."""

    @staticmethod
    def is_protected_role(group: Union[Group, Groups, str]) -> bool:
        """Проверяет, является ли группа защищенной доменной ролью подсистем.

        Защищенные роли обладают полным иммунитетом и никогда не удаляются
        при кадровой синхронизации должностей.

        Args:
            group (Union[Group, Groups, str]): Объект группы Django или ее наименование.

        Returns:
            bool: True, если группа защищена от сброса, иначе False.
        """
        name = group.name if hasattr(group, "name") else str(group)
        name = name.strip()
        if name in PROTECTED_ROLE_NAMES:
            return True
        return any(name.startswith(prefix) for prefix in PROTECTED_ROLE_PREFIXES)

    @staticmethod
    def get_job_group_ids_for_user(user: DataBaseUser) -> Set[int]:
        """Возвращает множество ID групп, привязанных к текущей штатной должности сотрудника.

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Set[int]: Множество ID групп должности из Job.group.
        """
        profile = getattr(user, "user_work_profile", None)
        job = getattr(profile, "job", None) if profile else None
        if not job:
            return set()
        return set(job.group.values_list("id", flat=True))

    @classmethod
    def get_job_groups_for_user(cls, user: DataBaseUser) -> Set[Group]:
        """Возвращает множество базовых групп Django (Group), привязанных к должности сотрудника.

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Set[Group]: Множество базовых групп должности.
        """
        group_ids = cls.get_job_group_ids_for_user(user)
        if not group_ids:
            return set()
        return set(Group.objects.filter(id__in=group_ids))

    @staticmethod
    def get_personal_group_ids_for_user(user: DataBaseUser) -> Set[int]:
        """Возвращает множество ID персональных групп сотрудника.

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Set[int]: Множество ID персональных групп из user.personal_groups.
        """
        if hasattr(user, "personal_groups"):
            return set(user.personal_groups.values_list("id", flat=True))
        return set()

    @staticmethod
    def get_personal_groups_for_user(user: DataBaseUser) -> Set[Group]:
        """Возвращает множество индивидуально назначенных дополнительных групп сотрудника.

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Set[Group]: Множество персональных групп из user.personal_groups.
        """
        if hasattr(user, "personal_groups"):
            return set(user.personal_groups.all())
        return set()

    @classmethod
    def get_protected_roles_for_user(cls, user: DataBaseUser) -> Set[Group]:
        """Возвращает множество защищенных доменных ролей, которые уже имеются у пользователя.

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Set[Group]: Множество защищенных групп ЛПК и сервисов.
        """
        current_groups = set(user.groups.all())
        return {g for g in current_groups if cls.is_protected_role(g)}

    @classmethod
    @transaction.atomic
    def sync_user_groups(cls, user: DataBaseUser) -> Dict[str, Any]:
        """Атомарно синхронизирует действующие права пользователя по трехуровневой модели.

        Формирует итоговый набор прав:
            Итоговые права = Группы должности ∪ Персональные группы ∪ Защищенные роли подсистем.

        Никогда не сбрасывает роли ЛПК, почтовых администраторов и персональные права.
        Удаляет только устаревшие должностные группы (например, при кадровом переводе).

        Args:
            user (DataBaseUser): Пользователь системы.

        Returns:
            Dict[str, Any]: Статистика синхронизации (added, removed, total, retained).
        """
        if not user or not user.is_active or user.username == "proxmox":
            return {"skipped": True, "added": 0, "removed": 0, "total": 0}

        current_groups_map = {g.id: g for g in user.groups.all()}
        current_ids = set(current_groups_map.keys())

        job_ids = cls.get_job_group_ids_for_user(user)
        personal_ids = cls.get_personal_group_ids_for_user(user)
        protected_ids = {
            gid for gid, g in current_groups_map.items()
            if cls.is_protected_role(g)
        }

        target_ids = job_ids | personal_ids | protected_ids

        ids_to_add = target_ids - current_ids
        ids_to_remove = current_ids - target_ids

        if ids_to_remove:
            user.groups.remove(*ids_to_remove)
        if ids_to_add:
            user.groups.add(*ids_to_add)

        retained_personal = len(personal_ids & current_ids)
        retained_protected = len(protected_ids)

        logger.debug(
            "Синхронизация прав %s: добавлено=%d, удалено=%d, сохранено (перс=%d, домен=%d)",
            user.username,
            len(ids_to_add),
            len(ids_to_remove),
            retained_personal,
            retained_protected,
        )

        return {
            "skipped": False,
            "added": len(ids_to_add),
            "removed": len(ids_to_remove),
            "total": len(target_ids),
            "retained_personal": retained_personal,
            "retained_protected": retained_protected,
        }

    @classmethod
    def sync_all_users_groups(cls, exclude_inactive: bool = True) -> Dict[str, Any]:
        """Выполняет безопасную пакетную синхронизацию прав для всех пользователей системы.

        Используется в представлении свойств портала (PortalPropertyList / update=1)
        вместо старого разрушительного алгоритма groups.clear().

        Args:
            exclude_inactive (bool): Исключать ли деактивированных пользователей (по умолчанию True).

        Returns:
            Dict[str, Any]: Сводная статистика обработки.
        """
        queryset = DataBaseUser.objects.all().exclude(username="proxmox")
        if exclude_inactive:
            queryset = queryset.filter(is_active=True)

        queryset = queryset.select_related(
            "user_work_profile",
            "user_work_profile__job",
        ).prefetch_related(
            "groups",
            "personal_groups",
            "user_work_profile__job__group",
        )

        total_users = 0
        total_added = 0
        total_removed = 0
        total_retained_personal = 0
        total_retained_protected = 0
        errors_count = 0

        for user_obj in queryset:
            try:
                stat = cls.sync_user_groups(user_obj)
                if not stat.get("skipped"):
                    total_users += 1
                    total_added += stat.get("added", 0)
                    total_removed += stat.get("removed", 0)
                    total_retained_personal += stat.get("retained_personal", 0)
                    total_retained_protected += stat.get("retained_protected", 0)
            except Exception as exc:
                errors_count += 1
                logger.exception("Ошибка синхронизации прав у пользователя %s: %s", user_obj, exc)

        summary = {
            "total_users": total_users,
            "total_added": total_added,
            "total_removed": total_removed,
            "total_retained_personal": total_retained_personal,
            "total_retained_protected": total_retained_protected,
            "errors_count": errors_count,
            "message": (
                f"Права успешно актуализированы для {total_users} сотрудников. "
                f"Добавлено прав: {total_added}, отозвано устаревших: {total_removed}. "
                f"Сохранено персональных прав: {total_retained_personal}, "
                f"защищенных ролей ЛПК/подсистем: {total_retained_protected}."
            ),
        }
        logger.info("Пакетная синхронизация прав завершена: %s", summary["message"])
        return summary

    @classmethod
    def get_permissions_audit_report(cls) -> List[Dict[str, Any]]:
        """Формирует отчет аудита прав для ревизии нестандартных доступов.

        Находит всех активных пользователей, у которых есть группы,
        не входящие в штатную должность, не являющиеся доменными ролями ЛПК
        и еще не перенесенные в personal_groups.

        Returns:
            List[Dict[str, Any]]: Список сотрудников с описанием их нестандартных прав.
        """
        users = DataBaseUser.objects.filter(is_active=True).exclude(username="proxmox").select_related(
            "user_work_profile",
            "user_work_profile__job",
            "user_work_profile__divisions",
        ).prefetch_related(
            "groups",
            "personal_groups",
            "user_work_profile__job__group",
        )

        audit_results: List[Dict[str, Any]] = []

        for user in users:
            current_groups = list(user.groups.all())
            if not current_groups:
                continue

            current_groups_map = {g.id: g for g in current_groups}
            current_ids = set(current_groups_map.keys())

            job_ids = cls.get_job_group_ids_for_user(user)
            personal_ids = cls.get_personal_group_ids_for_user(user)
            protected_ids = {
                gid for gid, g in current_groups_map.items()
                if cls.is_protected_role(g)
            }

            unclassified_ids = current_ids - job_ids - personal_ids - protected_ids

            if unclassified_ids:
                profile = getattr(user, "user_work_profile", None)
                audit_results.append({
                    "user_id": user.pk,
                    "full_name": user.get_title(),
                    "username": user.username,
                    "job_name": str(profile.job) if (profile and profile.job) else "—",
                    "division_name": str(profile.divisions) if (profile and profile.divisions) else "—",
                    "unclassified_groups": [
                        current_groups_map[gid].name
                        for gid in sorted(unclassified_ids, key=lambda i: current_groups_map[i].name)
                    ],
                    "personal_groups": [
                        current_groups_map[gid].name
                        for gid in sorted(personal_ids & current_ids, key=lambda i: current_groups_map[i].name)
                    ],
                    "domain_roles": [
                        current_groups_map[gid].name
                        for gid in sorted(protected_ids, key=lambda i: current_groups_map[i].name)
                    ],
                })

        return audit_results

    @classmethod
    @transaction.atomic
    def promote_extra_groups_to_personal(cls, user_id: int) -> int:
        """Переносит все нестандартные группы пользователя в personal_groups.

        Позволяет администратору в один клик зафиксировать исторические права
        пользователя как персональные, чтобы они не терялись при синхронизации.

        Args:
            user_id (int): Идентификатор пользователя DataBaseUser.

        Returns:
            int: Количество групп, перенесенных в персональные.
        """
        user = DataBaseUser.objects.filter(pk=user_id).first()
        if not user:
            return 0

        current_groups_map = {g.id: g for g in user.groups.all()}
        current_ids = set(current_groups_map.keys())

        job_ids = cls.get_job_group_ids_for_user(user)
        personal_ids = cls.get_personal_group_ids_for_user(user)
        protected_ids = {
            gid for gid, g in current_groups_map.items()
            if cls.is_protected_role(g)
        }

        extra_ids = current_ids - job_ids - personal_ids - protected_ids
        if extra_ids:
            user.personal_groups.add(*extra_ids)
            return len(extra_ids)
        return 0

    @classmethod
    @transaction.atomic
    def promote_all_extra_groups_to_personal(cls) -> Dict[str, int]:
        """Массово переносит все нестандартные группы всех пользователей в personal_groups.

        Позволяет администратору одной кнопкой сохранить текущие назначенные
        дополнительные группы сотрудников как персональные права без их потери.

        Returns:
            Dict[str, int]: Словарь с количеством обработанных сотрудников ('users_count')
                и суммарным количеством зафиксированных персональных групп ('groups_count').
        """
        audit_report = cls.get_permissions_audit_report()
        total_promoted_users = 0
        total_promoted_groups = 0

        for item in audit_report:
            user_id = item.get("user_id")
            if not user_id:
                continue
            count = cls.promote_extra_groups_to_personal(user_id)
            if count > 0:
                total_promoted_users += 1
                total_promoted_groups += count

        logger.info(
            "Массовое назначение персональных групп: сотрудников=%d, групп=%d",
            total_promoted_users,
            total_promoted_groups,
        )
        return {
            "users_count": total_promoted_users,
            "groups_count": total_promoted_groups,
        }

    @classmethod
    @transaction.atomic
    def add_personal_group(cls, user_id: int, group_id: int) -> Tuple[bool, str]:
        """Добавляет группу доступа в персональные права сотрудника.

        Args:
            user_id (int): Идентификатор пользователя DataBaseUser.
            group_id (int): Идентификатор группы доступа Group.

        Returns:
            Tuple[bool, str]: Флаг успешности и текстовое сообщение о результате.
        """
        user = DataBaseUser.objects.filter(pk=user_id).first()
        if not user:
            return False, "Пользователь не найден."

        group = Group.objects.filter(pk=group_id).first()
        if not group:
            return False, "Группа доступа не найдена."

        if user.personal_groups.filter(pk=group.pk).exists():
            return True, f"Группа «{group.name}» уже назначена как персональное право сотрудника."

        user.personal_groups.add(group)
        logger.info(
            "Администратор назначил персональную группу '%s' пользователю %s (ID=%d)",
            group.name,
            user.username,
            user.pk,
        )
        return True, f"Группа «{group.name}» успешно назначена как персональное право."

    @classmethod
    @transaction.atomic
    def remove_personal_group(cls, user_id: int, group_id: int) -> Tuple[bool, str]:
        """Отзывает группу доступа из персональных прав сотрудника.

        Args:
            user_id (int): Идентификатор пользователя DataBaseUser.
            group_id (int): Идентификатор группы доступа Group.

        Returns:
            Tuple[bool, str]: Флаг успешности и текстовое сообщение о результате.
        """
        user = DataBaseUser.objects.filter(pk=user_id).first()
        if not user:
            return False, "Пользователь не найден."

        group = Group.objects.filter(pk=group_id).first()
        if not group:
            return False, "Группа доступа не найдена."

        if not user.personal_groups.filter(pk=group.pk).exists():
            return False, f"Группа «{group.name}» не числится в персональных правах сотрудника."

        user.personal_groups.remove(group)
        logger.info(
            "Администратор отозвал персональную группу '%s' у пользователя %s (ID=%d)",
            group.name,
            user.username,
            user.pk,
        )
        return True, f"Персональное право «{group.name}» успешно отозвано."

    @classmethod
    def get_user_permissions_summary(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает агрегированный срез действующих прав конкретного сотрудника по категориям.

        Args:
            user_id (int): Идентификатор пользователя DataBaseUser.

        Returns:
            Optional[Dict[str, Any]]: Словарь с метаданными пользователя, должностными,
                персональными, защищенными и нераспределенными правами, либо None.
        """
        user = DataBaseUser.objects.filter(pk=user_id).select_related(
            "user_work_profile",
            "user_work_profile__job",
            "user_work_profile__divisions",
        ).prefetch_related(
            "groups",
            "personal_groups",
            "user_work_profile__job__group",
        ).first()
        if not user:
            return None

        current_groups_map = {g.id: g for g in user.groups.all()}
        current_ids = set(current_groups_map.keys())

        job_ids = cls.get_job_group_ids_for_user(user)
        personal_ids = cls.get_personal_group_ids_for_user(user)
        protected_ids = {
            gid for gid, g in current_groups_map.items()
            if cls.is_protected_role(g)
        }

        unclassified_ids = current_ids - job_ids - personal_ids - protected_ids

        profile = getattr(user, "user_work_profile", None)
        job = getattr(profile, "job", None) if profile else None
        division = getattr(profile, "divisions", None) if profile else None

        job_groups_objs = Group.objects.filter(id__in=job_ids)
        personal_groups_objs = user.personal_groups.all()

        job_str = str(job).strip() if job else ""
        division_str = str(division).strip() if division else ""
        domain_list = [
            {"id": gid, "name": current_groups_map[gid].name}
            for gid in sorted(protected_ids, key=lambda i: current_groups_map[i].name)
        ]
        unclassified_list = [
            {"id": gid, "name": current_groups_map[gid].name}
            for gid in sorted(unclassified_ids, key=lambda i: current_groups_map[i].name)
        ]

        return {
            "user_id": user.pk,
            "full_name": user.get_title(),
            "user_name": user.get_title(),
            "username": user.username,
            "job_name": job_str if job_str and job_str != "—" else "",
            "division_name": division_str if division_str and division_str != "—" else "",
            "job_groups": [
                {"id": g.id, "name": g.name}
                for g in sorted(job_groups_objs, key=lambda x: x.name)
            ],
            "personal_groups": [
                {"id": g.id, "name": g.name}
                for g in sorted(personal_groups_objs, key=lambda x: x.name)
            ],
            "domain_roles": domain_list,
            "domain_groups": domain_list,
            "unclassified_groups": unclassified_list,
            "other_groups": unclassified_list,
        }


