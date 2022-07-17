# Generated by Django 4.0.6 on 2022-07-17 13:55

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contracts_app', '0003_contract_divisions_alter_contract_type_property'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='employee',
            field=models.ManyToManyField(null=True, to=settings.AUTH_USER_MODEL, verbose_name='Ответственное лицо'),
        ),
    ]
