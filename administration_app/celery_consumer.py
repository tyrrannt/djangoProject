"""Асинхронный потребитель WebSockets для потоковой трансляции состояния Celery в реальном времени.

Обеспечивает непрерывную передачу среза активных задач, состояния воркеров,
метрик очередей Redis и истории выполнения в браузер администратора без задержек.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from administration_app.celery_monitor_service import CeleryMonitorService

logger = logging.getLogger(__name__)


class CeleryMonitorConsumer(AsyncWebsocketConsumer):
    """WebSocket-консьюмер реального времени для дашборда мониторинга задач Celery.

    Attributes:
        is_running (bool): Флаг активности цикла фоновой рассылки телеметрии.
        refresh_interval (float): Периодичность обновления данных в секундах.
    """

    def __init__(self, *args, **kwargs):
        """Инициализация экземпляра консьюмера."""
        super().__init__(*args, **kwargs)
        self.is_running: bool = False
        self.refresh_interval: float = 2.5

    async def connect(self):
        """Устанавливает WebSocket-соединение с авторизацией администратора и запускает Live-поток.

        Raises:
            Exception: При сбоях отправки начального пакета данных.
        """
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not (user.is_staff or user.is_superuser):
            logger.warning("[CeleryConsumer] Отклонено неавторизованное WebSocket-соединение.")
            await self.close()
            return

        await self.accept()
        self.is_running = True

        # Запуск асинхронного цикла трансляции
        asyncio.create_task(self._telemetry_broadcast_loop())

    async def _telemetry_broadcast_loop(self):
        """Внутренний асинхронный цикл регулярного сбора и отправки телеметрии клиенту."""
        try:
            while self.is_running:
                payload = await sync_to_async(
                    CeleryMonitorService.get_comprehensive_payload,
                    thread_sensitive=False,
                )()
                await self.send(text_data=json.dumps(payload, ensure_ascii=False))
                await asyncio.sleep(self.refresh_interval)
        except Exception as exc:
            logger.debug("[CeleryConsumer] Завершение цикла трансляции: %s", exc)
            self.is_running = False

    async def receive(self, text_data: Optional[str] = None, bytes_data: Optional[bytes] = None):
        """Обрабатывает входящие команды от клиента через WebSocket (запрос немедленного обновления, пинг).

        Args:
            text_data (Optional[str]): Текстовое сообщение в формате JSON.
            bytes_data (Optional[bytes]): Бинарные данные (не используются).
        """
        if not text_data:
            return

        try:
            msg = json.loads(text_data)
            action = msg.get("action")

            if action in ("refresh", "request_update"):
                payload = await sync_to_async(
                    CeleryMonitorService.get_comprehensive_payload,
                    thread_sensitive=False,
                )()
                await self.send(text_data=json.dumps(payload, ensure_ascii=False))

            elif action == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))

        except Exception as exc:
            logger.debug("[CeleryConsumer] Ошибка обработки входящего сообщения: %s", exc)

    async def disconnect(self, close_code: int):
        """Корректно останавливает цикл трансляции при разрыве соединения.

        Args:
            close_code (int): Код закрытия WebSocket-соединения.
        """
        self.is_running = False
