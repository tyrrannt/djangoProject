# Generated by Django 4.2 on 2023-04-28 18:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0016_approvaloficialmemoprocess_accepted_accounting_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='placeproductionactivity',
            name='short_name',
            field=models.CharField(default='', max_length=3, verbose_name=''),
        ),
    ]
