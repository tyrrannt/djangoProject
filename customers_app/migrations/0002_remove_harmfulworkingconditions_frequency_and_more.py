# Generated by Django 4.1.3 on 2022-11-24 15:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='harmfulworkingconditions',
            name='frequency',
        ),
        migrations.AddField(
            model_name='harmfulworkingconditions',
            name='frequency_inspection',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Периодичность осмотров'),
        ),
        migrations.AddField(
            model_name='harmfulworkingconditions',
            name='frequency_multiplicity',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Кратность осмотров'),
        ),
    ]