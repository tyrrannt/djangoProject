# Generated by Django 5.0.3 on 2024-04-24 17:52

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics_app", "0008_alter_waybill_comment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="waybill",
            name="content",
            field=models.TextField(default="", verbose_name="Содержание"),
        ),
    ]