# Generated data migration to create 'Ответственные за тестирование' group

from django.db import migrations


def create_testing_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Ответственные за тестирование")


def remove_testing_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Ответственные за тестирование").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("testing_app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_testing_manager_group, remove_testing_manager_group),
    ]
