# Generated by Django 4.2 on 2023-05-08 22:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0035_officialmemo_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='prepaid_expense_summ',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Сумма авансового отчета'),
        ),
    ]
