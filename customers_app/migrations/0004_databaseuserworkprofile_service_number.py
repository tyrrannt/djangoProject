# Generated by Django 4.1.6 on 2023-02-22 08:39

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('customers_app', '0003_alter_databaseuser_user_profile_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='databaseuserworkprofile',
            name='service_number',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='Табельный номер'),
        ),
    ]
