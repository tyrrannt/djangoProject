# Generated by Django 4.1.6 on 2023-02-20 17:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0033_medical_type_inspection_medical_type_of_inspection_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medical',
            name='type_inspection',
            field=models.CharField(blank=True, choices=[('1', 'Предварительный'), ('2', 'Периодический'), ('3', 'Внеплановый')], default='', max_length=15, verbose_name='Тип осмотра'),
        ),
        migrations.AlterField(
            model_name='medical',
            name='type_of_inspection',
            field=models.CharField(blank=True, choices=[('1', 'Медицинский осмотр'), ('2', 'Психиатрическое освидетельствование')], default='', max_length=40, verbose_name='Вид осмотра'),
        ),
    ]
