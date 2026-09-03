"""Миграция данных для создания группы 'Администраторы почты' и назначения ей разрешений."""

from django.db import migrations


def create_mail_admins_group(apps, schema_editor):
    """Создает группу 'Администраторы почты' и привязывает разрешение manage_mailboxes."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.get_or_create(name="Администраторы почты")

    try:
        perm = Permission.objects.filter(codename="manage_mailboxes").first()
        if perm:
            group.permissions.add(perm)
    except Exception:
        pass


def remove_mail_admins_group(apps, schema_editor):
    """Откат миграции (безопасный no-op, чтобы сохранить привязки пользователей)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mailbox_app", "0004_mailbox_and_scheduledemail_mailbox"),
    ]

    operations = [
        migrations.RunPython(create_mail_admins_group, remove_mail_admins_group),
    ]
