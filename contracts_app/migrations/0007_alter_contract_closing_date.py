# Generated by Django 4.0.6 on 2022-07-17 13:58

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('contracts_app', '0006_alter_contract_closing_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='closing_date',
            field=models.DateField(null=True, verbose_name='Дата закрытия договора'),
        ),
    ]
