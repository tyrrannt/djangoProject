# Generated by Django 4.0.6 on 2022-07-23 08:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts_app', '0017_contract_allowed_placed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='cost',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Стоимость'),
        ),
    ]
