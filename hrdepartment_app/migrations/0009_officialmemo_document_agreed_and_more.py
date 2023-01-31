# Generated by Django 4.1.3 on 2022-11-21 20:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hrdepartment_app', '0008_approvaloficialmemoprocess'),
    ]

    operations = [
        migrations.AddField(
            model_name='officialmemo',
            name='document_agreed',
            field=models.BooleanField(default=False, verbose_name='Документ не согласован'),
        ),
        migrations.AddField(
            model_name='officialmemo',
            name='document_not_agreed',
            field=models.BooleanField(default=False, verbose_name='Документ согласован'),
        ),
        migrations.AddField(
            model_name='officialmemo',
            name='reason_for_approval',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Примечание к согласованию'),
        ),
    ]