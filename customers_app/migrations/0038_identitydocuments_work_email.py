# Generated by Django 4.1 on 2022-08-27 09:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0037_alter_harmfulworkingconditions_frequency'),
    ]

    operations = [
        migrations.AddField(
            model_name='identitydocuments',
            name='work_email',
            field=models.EmailField(default='', max_length=254, verbose_name='Рабочий email'),
        ),
    ]
