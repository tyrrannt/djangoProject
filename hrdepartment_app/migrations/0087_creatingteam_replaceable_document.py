# Generated by Django 5.0.3 on 2024-03-28 13:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0086_alter_creatingteam_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="creatingteam",
            name="replaceable_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="hrdepartment_app.creatingteam",
            ),
        ),
    ]
