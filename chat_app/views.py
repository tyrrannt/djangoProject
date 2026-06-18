from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from .forms import CreateRoomForm
from django.contrib.auth import get_user_model
import json

User = get_user_model()

@login_required
def index(request):
    """
    Представление для создания виртуальной комнаты и приглашения участников.
    """
    if request.method == 'POST':
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            room_name = form.cleaned_data['room_name']
            invited_users = form.cleaned_data['users']
            
            # Мы можем сохранить информацию о приглашении или сразу перенаправить.
            # Для реализации "оповещения" мы будем использовать существующий PrivateMessageConsumer
            # или просто ожидать, что фронтенд отправит сигнал.
            # Но лучше сделать это через URL и передать список приглашенных в контекст.
            
            room_url = request.build_absolute_uri(reverse('chat_app:room', args=[room_name]))
            
            return render(request, 'chat_app/room_created.html', {
                'room_name': room_name,
                'room_url': room_url,
                'invited_users': invited_users
            })
    else:
        form = CreateRoomForm()
    
    return render(request, 'chat_app/index.html', {'form': form})

@login_required
def room(request, room_name):
    return render(request, 'room.html', {
        'room_name': room_name
    })