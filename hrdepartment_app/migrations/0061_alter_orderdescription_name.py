# Generated by Django 4.2.1 on 2023-08-07 13:30

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0060_remove_orderdescription_affiliation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderdescription",
            name="name",
            field=models.CharField(blank=True, max_length=250, verbose_name=""),
        ),
    ]