# Generated by Django 4.2 on 2023-04-27 15:40

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0013_approvaloficialmemoprocess_email_send'),
    ]

    operations = [
        migrations.AlterField(
            model_name='documentsjobdescription',
            name='document_date',
            field=models.DateField(default=django.utils.timezone.now, verbose_name='Дата документа'),
        ),
        migrations.AlterField(
            model_name='documentsorder',
            name='document_date',
            field=models.DateField(default=django.utils.timezone.now, verbose_name='Дата документа'),
        ),
    ]