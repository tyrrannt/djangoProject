from django.views.decorators.cache import cache_page

import sqlite3
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import MapSource
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def map_index(request):
    maps = MapSource.objects.filter(is_active=True)
    return render(request, 'map_viewer/index.html', {'maps': maps})


@login_required(login_url='/users/login/')
@cache_page(60 * 60 * 24)
def get_tile(request, map_id, z, x, y):
    map_source = get_object_or_404(MapSource, id=map_id)

    # 1. СЛОВАРЬ ОФФСЕТОВ (ваши данные)
    OFFSETS = {
        5: (2343, 1092), 6: (1171, 546), 7: (585, 273),
        8: (292, 136), 9: (146, 68), 10: (73, 34),
        11: (36, 17), 12: (18, 8)
    }

    # 2. ИНВЕРСИЯ ЗУМА
    db_z = 17 - z

    # 3. РАСЧЕТ КООРДИНАТ
    # Если мы используем CRS.Simple, Leaflet начнет с x=0, y=0.
    # Мы просто прибавляем это к минимальному значению в базе.
    min_x, min_y = OFFSETS.get(db_z, (0, 0))

    db_x = min_x + x
    # ВАЖНО: в CRS.Simple Y растет ВНИЗ, как и в большинстве БД (XYZ).
    # Поэтому просто прибавляем.
    db_y = min_y + y

    try:
        with sqlite3.connect(map_source.full_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT image FROM tiles WHERE z=? AND x=? AND y=? AND s=0 LIMIT 1",
                (db_z, db_x, db_y)
            )
            row = cursor.fetchone()

            if row:
                return HttpResponse(row['image'], content_type="image/png")
            else:
                # Если не нашли, отдаем пустой прозрачный пиксель (чтобы не было серых зон)
                return HttpResponse(
                    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x2e\xe4\x00\x00\x00\x00IEND\xaeB`\x82',
                    content_type="image/png"
                )
    except Exception as e:
        print(f"TILE ERROR: {e}")
        return HttpResponse(status=500)
