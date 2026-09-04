"""Миграция данных: синхронизация групп из auth_group в customers_app_groups."""

from django.db import migrations


def sync_auth_groups_to_customers_groups(apps, schema_editor):
    """Синхронизирует все существующие группы из auth_group в customers_app_groups."""
    Group = apps.get_model("auth", "Group")
    Groups = apps.get_model("customers_app", "Groups")

    existing_group_ids = set(Groups.objects.values_list("pk", flat=True))
    all_auth_ids = set(Group.objects.values_list("pk", flat=True))
    missing_ids = all_auth_ids - existing_group_ids

    if missing_ids:
        with schema_editor.connection.cursor() as cursor:
            for gid in missing_ids:
                cursor.execute(
                    "INSERT INTO customers_app_groups (group_ptr_id) VALUES (%s)",
                    [gid],
                )


def reverse_sync(apps, schema_editor):
    """Безопасный no-op при откате."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("customers_app", "0080_rename_customers_a_user_id_44f12d_idx_customers_a_user_id_6e3c2a_idx"),
    ]

    operations = [
        migrations.RunPython(sync_auth_groups_to_customers_groups, reverse_sync),
    ]
