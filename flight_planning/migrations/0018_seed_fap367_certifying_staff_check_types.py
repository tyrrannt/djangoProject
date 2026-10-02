# Generated for FAP-367 Certifying Staff Authorization Types on 2026-10-01

from django.db import migrations


def seed_certifying_staff_check_types(apps, schema_editor):
    """Создает виды периодических мероприятий подтверждающего персонала по ФАП-367."""
    PeriodicCheckType = apps.get_model('flight_planning', 'PeriodicCheckType')

    check_types_data = [
        {
            'code': 'CERT_STAFF_LINE',
            'defaults': {
                'name': 'Допуск подтверждающего персонала: Оперативное ТО',
                'validity_months': 24,
                'validity_days': 0,
                'applies_to': 'technicians',
                'order': 100,
                'is_active': True,
                'description': (
                    'Персональный допуск организации по ТО к оформлению свидетельств о ТО (CRS) '
                    'при выполнении оперативного технического обслуживания ВС в соответствии '
                    'с требованиями пп. 70-80, 117-122 ФАП-367.'
                ),
            },
        },
        {
            'code': 'CERT_STAFF_BASE',
            'defaults': {
                'name': 'Допуск подтверждающего персонала: Периодическое ТО',
                'validity_months': 24,
                'validity_days': 0,
                'applies_to': 'technicians',
                'order': 110,
                'is_active': True,
                'description': (
                    'Персональный допуск организации по ТО к оформлению свидетельств о ТО (CRS) '
                    'при выполнении периодического регламентного технического обслуживания ВС в соответствии '
                    'с требованиями пп. 70-80, 117-122 ФАП-367.'
                ),
            },
        },
    ]

    for item in check_types_data:
        PeriodicCheckType.objects.update_or_create(
            code=item['code'],
            defaults=item['defaults']
        )


def rollback_certifying_staff_check_types(apps, schema_editor):
    """Откат видов мероприятий подтверждающего персонала."""
    PeriodicCheckType = apps.get_model('flight_planning', 'PeriodicCheckType')
    PeriodicCheckType.objects.filter(code__in=['CERT_STAFF_LINE', 'CERT_STAFF_BASE']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('flight_planning', '0017_setup_lpc_domain_roles'),
    ]

    operations = [
        migrations.RunPython(
            seed_certifying_staff_check_types,
            reverse_code=rollback_certifying_staff_check_types
        ),
    ]
