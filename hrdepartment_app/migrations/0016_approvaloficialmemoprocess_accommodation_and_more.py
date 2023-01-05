# Generated by Django 4.1.5 on 2023-01-28 10:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0015_remove_approvaloficialmemoprocess_document_agreed'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='accommodation',
            field=models.CharField(blank=True, choices=[('1', 'Квартира'), ('2', 'Гостиница')], default='', max_length=9, verbose_name='Проживание'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='order_date',
            field=models.DateField(null=True, verbose_name='Дата приказа'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='order_number',
            field=models.CharField(default='', max_length=20, null=True, verbose_name='Номер приказа'),
        ),
    ]
