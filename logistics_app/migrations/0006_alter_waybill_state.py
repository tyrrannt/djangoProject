# Generated by Django 5.0.3 on 2024-03-30 11:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("logistics_app", "0005_waybill_content_waybill_sender_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="waybill",
            name="state",
            field=models.CharField(
                choices=[
                    ("0", "Не обработана"),
                    ("1", "Обработана"),
                    ("2", "Отправлена"),
                    ("3", "Принята"),
                    ("4", "Отклонена"),
                ],
                default="0",
                max_length=100,
                verbose_name="Состояние",
            ),
        ),
    ]
