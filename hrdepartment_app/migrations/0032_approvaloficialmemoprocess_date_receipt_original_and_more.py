# Generated by Django 4.2 on 2023-05-05 10:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0031_approvaloficialmemoprocess_submitted_for_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='date_receipt_original',
            field=models.DateField(blank=True, null=True, verbose_name='Дата получения'),
        ),
        migrations.AddField(
            model_name='approvaloficialmemoprocess',
            name='originals_docs_comment',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Примечание'),
        ),
    ]
