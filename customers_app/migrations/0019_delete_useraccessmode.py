# Generated by Django 4.1.7 on 2023-03-14 07:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('customers_app', '0018_remove_databaseuser_access_level'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UserAccessMode',
        ),
    ]
