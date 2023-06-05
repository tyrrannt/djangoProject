# Generated by Django 4.2.1 on 2023-06-05 11:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0048_medical_medical_direction2_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TypesUserworktime',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_key', models.CharField(default='', max_length=37, verbose_name='Уникальный номер')),
                ('description', models.CharField(default='', max_length=150, verbose_name='Наименование')),
                ('letter_code', models.CharField(default='', max_length=5, verbose_name='Буквенный код')),
                ('active', models.BooleanField(default=False, verbose_name='Используется')),
            ],
            options={
                'verbose_name': 'Вид использования рабочего времени',
                'verbose_name_plural': 'Виды использования рабочего времени',
            },
        ),
    ]
