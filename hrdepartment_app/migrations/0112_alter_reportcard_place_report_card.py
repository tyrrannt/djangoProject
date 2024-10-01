# Generated by Django 5.0.6 on 2024-09-25 13:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hrdepartment_app", "0111_outfitcard_outfit_card_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reportcard",
            name="place_report_card",
            field=models.ManyToManyField(
                blank=True,
                related_name="place_report_card",
                to="hrdepartment_app.placeproductionactivity",
                verbose_name="МПД",
            ),
        ),
    ]