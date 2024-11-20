# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def room(request, room_name):
    return render(request, 'room.html', {
        'room_name': room_name
    })