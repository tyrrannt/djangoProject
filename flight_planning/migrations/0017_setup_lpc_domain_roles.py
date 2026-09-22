# Generated for LPC Domain-Based Roles & Permissions on 2026-09-22

from django.db import migrations


def setup_lpc_domain_roles(apps, schema_editor):
    """Создает стандартные доменные группы Летно-производственного комплекса (ЛПК)."""
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Конфигурация групп ЛПК
    groups_config = {
        '[ЛПК] Руководство': [
            'can_view_flight_planning',
            'can_view_flight_reports',
            'view_flightcrew',
            'view_crewmember',
            'view_pilotassignment',
            'view_aircraftmovement',
            'view_flightcrewnote',
            'view_flightplanningdocument',
            'view_periodiccheckrecord',
            'view_periodicchecktype',
            'view_employeestatusrecord',
            'view_employeestatustype',
        ],
        '[ЛПК] Диспетчеры планирования': [
            'can_manage_flight_planning',
            'can_view_flight_planning',
            'can_view_flight_reports',
            'add_flightcrew',
            'change_flightcrew',
            'delete_flightcrew',
            'view_flightcrew',
            'add_crewmember',
            'change_crewmember',
            'delete_crewmember',
            'view_crewmember',
            'add_pilotassignment',
            'change_pilotassignment',
            'delete_pilotassignment',
            'view_pilotassignment',
            'add_aircraftmovement',
            'change_aircraftmovement',
            'delete_aircraftmovement',
            'view_aircraftmovement',
            'add_flightcrewnote',
            'change_flightcrewnote',
            'delete_flightcrewnote',
            'view_flightcrewnote',
            'add_flightplanningdocument',
            'change_flightplanningdocument',
            'view_flightplanningdocument',
            'add_periodiccheckrecord',
            'change_periodiccheckrecord',
            'delete_periodiccheckrecord',
            'view_periodiccheckrecord',
            'add_employeestatusrecord',
            'change_employeestatusrecord',
            'delete_employeestatusrecord',
            'view_employeestatusrecord',
        ],
        '[ЛПК] Инженерная служба (ИАС)': [
            'can_view_flight_planning',
            'can_view_flight_reports',
            'view_flightcrew',
            'view_pilotassignment',
            'add_aircraftmovement',
            'change_aircraftmovement',
            'delete_aircraftmovement',
            'view_aircraftmovement',
            'add_periodiccheckrecord',
            'change_periodiccheckrecord',
            'view_periodiccheckrecord',
            'add_employeestatusrecord',
            'change_employeestatusrecord',
            'view_employeestatusrecord',
        ],
        '[ЛПК] Летная служба': [
            'can_view_flight_planning',
            'can_view_flight_reports',
            'view_flightcrew',
            'view_pilotassignment',
            'view_aircraftmovement',
            'add_periodiccheckrecord',
            'change_periodiccheckrecord',
            'view_periodiccheckrecord',
            'add_employeestatusrecord',
            'change_employeestatusrecord',
            'view_employeestatusrecord',
        ],
        '[ЛПК] Кадры и охрана труда': [
            'can_view_flight_planning',
            'view_periodiccheckrecord',
            'add_periodiccheckrecord',
            'change_periodiccheckrecord',
            'view_employeestatusrecord',
            'add_employeestatusrecord',
            'change_employeestatusrecord',
        ],
        '[ЛПК] Летный состав': [
            'can_view_flight_planning',
            'view_flightcrew',
            'view_pilotassignment',
            'view_aircraftmovement',
            'view_flightcrewnote',
            'add_flightcrewnote',
            'view_periodiccheckrecord',
            'view_employeestatusrecord',
        ],
    }

    for group_name, perm_codenames in groups_config.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        perms = Permission.objects.filter(codename__in=perm_codenames)
        for perm in perms:
            group.permissions.add(perm)

    # Автоматически синхронизируем пользователей из общей группы 'Руководство' в '[ЛПК] Руководство'
    leadership_group = Group.objects.filter(name='Руководство').first()
    lpc_leadership_group = Group.objects.filter(name='[ЛПК] Руководство').first()
    if leadership_group and lpc_leadership_group:
        for user in leadership_group.user_set.all():
            lpc_leadership_group.user_set.add(user)


def rollback_lpc_domain_roles(apps, schema_editor):
    """Откатывает создание групп ЛПК при отмене миграции."""
    Group = apps.get_model('auth', 'Group')
    lpc_groups = [
        '[ЛПК] Руководство',
        '[ЛПК] Диспетчеры планирования',
        '[ЛПК] Инженерная служба (ИАС)',
        '[ЛПК] Летная служба',
        '[ЛПК] Кадры и охрана труда',
        '[ЛПК] Летный состав',
    ]
    Group.objects.filter(name__in=lpc_groups).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('flight_planning', '0016_aviationweatherstation_region'),
        ('auth', '__latest__'),
    ]

    operations = [
        migrations.RunPython(setup_lpc_domain_roles, rollback_lpc_domain_roles),
    ]
