# Generated by Django 5.0.3 on 2024-03-28 07:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "hrdepartment_app",
            "0080_alter_businessprocessdirection_business_process_type",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="placeproductionactivity",
            name="additional_payment",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name="Дополнительная оплата",
            ),
        ),
    ]