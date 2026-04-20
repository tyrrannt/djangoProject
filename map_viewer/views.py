import os
import sqlite3
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import MapSource


# @login_required(login_url='/customers/login/')
def map_index(request):
    maps = MapSource.objects.filter(is_active=True)
    return render(request, 'map_viewer/index.html', {'maps': maps})


from django.views.decorators.cache import cache_page

import sqlite3
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from .models import MapSource


def get_tile(request, map_id, z, x, y):
    map_obj = get_object_or_404(MapSource, id=map_id, is_active=True)

    try:
        conn = sqlite3.connect(map_obj.full_path)
        cursor = conn.cursor()

        # ВАЖНО: SQLite tiles обычно в TMS (y инвертирован)
        y = (1 << int(z)) - 1 - int(y)

        cursor.execute(
            "SELECT image FROM tiles WHERE x=? AND y=? AND z=? LIMIT 1",
            (x, y, z)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return HttpResponse(row[0], content_type="image/png")

    except Exception:
        pass

    raise Http404("Tile not found")

# @cache_page(60 * 60 * 24)
# @login_required(login_url='/customers/login/')
# def get_tile(request, map_id, z, x, y):
#     map_source = get_object_or_404(MapSource, id=map_id)
#
#     # 1. Попробуем альтернативную инверсию или прямой Y
#     # Если стандартный TMS не сработал, пробуем просто y или y со смещением
#     db_z = 17 - z
#     # По вашим логам: Leaflet просит y=81, в базе это 141.
#     # Разница составляет +60.
#     factor = 2 ** (z - 8)
#
#     # Смещение по X (правее): 300 - 152 = 148
#     db_x = x + int(148 * factor)
#
#     # Смещение по Y (разворачиваем/сдвигаем):
#     # Попробуем прямое смещение без инверсии (2**z - 1 - y)
#     db_y = y + int(60 * factor)
#
#     try:
#         with sqlite3.connect(map_source.full_path) as conn:
#             cursor = conn.cursor()
#             cursor.execute(
#                 "SELECT image FROM tiles WHERE z=? AND x=? AND y=? AND s=0 LIMIT 1",
#                 (z, db_x, db_y)
#             )
#             row = cursor.fetchone()
#
#             if row:
#                 return HttpResponse(row[0], content_type="image/png")
#             else:
#                 # Если не нашли, попробуем на всякий случай "развернутый" вариант
#                 # tms_y = (2**z - 1) - y + смещение
#                 alt_tms_y = ((2 ** z) - 1 - y) - int(33 * factor)
#                 cursor.execute(
#                     "SELECT image FROM tiles WHERE z=? AND x=? AND y=? AND s=0 LIMIT 1",
#                     (z, db_x, alt_tms_y)
#                 )
#                 row = cursor.fetchone()
#                 if row:
#                     return HttpResponse(row[0], content_type="image/png")
#
#                 return HttpResponse(
#                     b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\x2e\xe4\x00\x00\x00\x00IEND\xaeB`\x82',
#                     content_type="image/png"
#                 )
#     except Exception:
#         return HttpResponse(status=500)
