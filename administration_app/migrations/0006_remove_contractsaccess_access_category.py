# Generated by Django 4.1.1 on 2022-09-13 14:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('administration_app', '0005_alter_contractsaccess_authorized_person'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contractsaccess',
            name='access_category',
        ),
    ]
