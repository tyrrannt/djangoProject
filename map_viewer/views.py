import os
import sqlite3
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import MapSource


@login_required(login_url='/customers/login/')
def map_index(request):
    maps = MapSource.objects.filter(is_active=True)
    return render(request, 'map_viewer/index.html', {'maps': maps})


@login_required(login_url='/customers/login/')
def get_tile(request, map_id, z, x, y):
    map_source = get_object_or_404(MapSource, id=map_id)

    # Формула инверсии Y для MBTiles (TMS)
    tms_y = (2 ** z) - 1 - y

    try:
        with sqlite3.connect(map_source.full_path) as conn:
            cursor = conn.cursor()
            # s=0 всегда, согласно вашим данным
            cursor.execute(
                "SELECT image FROM tiles WHERE z=? AND x=? AND y=? AND s=0 LIMIT 1",
                (z, x, tms_y)
            )
            row = cursor.fetchone()

            if row:
                # Если тайл найден в базе
                return HttpResponse(row[0], content_type="image/png")
            else:
                # Если тайла нет, возвращаем прозрачную заглушку
                # Это предотвращает появление серых квадратов "Tile not found"
                return HttpResponse(
                    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x2e\xe4\x00\x00\x00\x00IEND\xaeB`\x82',
                    content_type="image/png"
                )
    except Exception as e:
        print(f"Ошибка при чтении тайла: {e}")
        return HttpResponse(status=500)