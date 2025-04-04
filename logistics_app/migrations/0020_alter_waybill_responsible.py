# Generated by Django 5.0.6 on 2025-04-04 08:31

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics_app", "0019_grade_nomenclatureunit_nomenclaturegroup_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="waybill",
            name="responsible",
            field=models.ForeignKey(
                blank=True,
                max_length=100,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="way_bill_responsible",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Получатель",
            ),
        ),
    ]
