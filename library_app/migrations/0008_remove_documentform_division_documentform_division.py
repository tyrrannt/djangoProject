# Generated by Django 5.0.3 on 2024-04-11 08:33

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers_app", "0047_alter_databaseuser_options"),
        ("library_app", "0007_documentform_division"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="documentform",
            name="division",
        ),
        migrations.AddField(
            model_name="documentform",
            name="division",
            field=models.ManyToManyField(
                blank=True,
                null=True,
                to="customers_app.division",
                verbose_name="Подразделение",
            ),
        ),
    ]
