# Generated by Django 4.1.6 on 2023-02-20 17:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0032_medicalorganisation'),
    ]

    operations = [
        migrations.AddField(
            model_name='medical',
            name='type_inspection',
            field=models.CharField(blank=True, choices=[('1', 'Предварительный'), ('2', 'Периодический'), ('3', 'Внеплановый')], default='', max_length=15, verbose_name='Статус'),
        ),
        migrations.AddField(
            model_name='medical',
            name='type_of_inspection',
            field=models.CharField(blank=True, choices=[('1', 'Медицинский осмотр'), ('2', 'Психиатрическое освидетельствование')], default='', max_length=40, verbose_name='Статус'),
        ),
        migrations.AlterField(
            model_name='medical',
            name='organisation',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='hrdepartment_app.medicalorganisation', verbose_name='Медицинская организация'),
        ),
    ]
