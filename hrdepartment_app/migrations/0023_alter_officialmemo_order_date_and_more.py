# Generated by Django 4.1.5 on 2023-02-03 07:48

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('hrdepartment_app', '0022_officialmemo_responsible'),
    ]

    operations = [
        migrations.AlterField(
            model_name='officialmemo',
            name='order_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата приказа'),
        ),
        migrations.AlterField(
            model_name='officialmemo',
            name='order_number',
            field=models.CharField(blank=True, default='', max_length=20, null=True, verbose_name='Номер приказа'),
        ),
    ]
