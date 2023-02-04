import pathlib

from django.db.models.signals import post_save
from django.dispatch import receiver

from contracts_app.models import Contract, contract_directory_path
from djangoProject.settings import BASE_DIR
