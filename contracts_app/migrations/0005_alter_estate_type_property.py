# Generated by Django 4.2.1 on 2023-06-24 10:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contracts_app', '0004_contract_actuality'),
    ]

    operations = [
        migrations.AlterField(
            model_name='estate',
            name='type_property',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='contracts_app.typeproperty', verbose_name='Тип имущества'),
        ),
    ]
