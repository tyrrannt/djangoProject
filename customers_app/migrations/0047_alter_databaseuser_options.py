# Generated by Django 5.0.1 on 2024-03-14 14:29

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("customers_app", "0046_alter_vacationschedulelist_options"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="databaseuser",
            options={
                "ordering": ["last_name"],
                "verbose_name": "Пользователь",
                "verbose_name_plural": "Пользователи",
            },
        ),
    ]