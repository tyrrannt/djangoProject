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

    # 1. Инверсия Y для TMS (стандарт для MBTiles)
    tms_y = (2 ** z) - 1 - y

    # 2. ПРИНУДИТЕЛЬНОЕ СМЕЩЕНИЕ (Корректировка под ваши данные в tales.txt)
    # Если зум 8, сдвигаем координаты туда, где лежат реальные данные
    db_x = x
    db_y = tms_y

    if z == 8:
        db_x = x + 148  # Сдвигаем 152 -> 300
        db_y = tms_y - 33  # Сдвигаем 174 -> 141

    # Для отладки в консоли
    print(f"Leaflet request: x={x}, y={y} (z={z})")
    print(f"DB search: x={db_x}, y={db_y}")

    try:
        with sqlite3.connect(map_source.full_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT image FROM tiles WHERE z=? AND x=? AND y=? AND s=0 LIMIT 1",
                (z, db_x, db_y)
            )
            row = cursor.fetchone()

            if row:
                print("--- SUCCESS ---")
                return HttpResponse(row[0], content_type="image/png")
            else:
                return HttpResponse(
                    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x2e\xe4\x00\x00\x00\x00IEND\xaeB`\x82',
                    content_type="image/png"
                )
    except Exception as e:
        return HttpResponse(status=500)