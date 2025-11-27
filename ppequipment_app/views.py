from django.shortcuts import render, redirect
from core import logger


# Create your views here.
def index(request):
    return redirect("/users/login/")
