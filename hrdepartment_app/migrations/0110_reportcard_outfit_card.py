# Generated by Django 5.0.6 on 2024-09-25 12:35

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0109_remove_reportcard_air_board_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportcard",
            name="outfit_card",
            field=models.ManyToManyField(
                blank=True,
                related_name="outfit_card_report_card",
                to="hrdepartment_app.outfitcard",
                verbose_name="Оперативные работы",
            ),
        ),
    ]