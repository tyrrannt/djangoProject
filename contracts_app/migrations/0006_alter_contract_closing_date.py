# Generated by Django 4.0.6 on 2022-07-17 13:57

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('contracts_app', '0005_alter_contract_employee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='closing_date',
            field=models.DateField(blank=True, verbose_name='Дата закрытия договора'),
        ),
    ]
