# Generated by Django 4.0.6 on 2022-07-18 20:00

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0015_alter_accesslevel_options_alter_address_options_and_more'),
        ('contracts_app', '0011_posts'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contract',
            name='divisions',
        ),
        migrations.AddField(
            model_name='contract',
            name='divisions',
            field=models.ManyToManyField(null=True, to='customers_app.division', verbose_name='Подразделение'),
        ),
    ]
