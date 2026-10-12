"""Контроллеры представлений для внутренних рейсов, посылок и приемочного контроля на МПД."""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from administration_app.utils import ajax_search
from customers_app.models import DataBaseUser, Division
from hrdepartment_app.models import PlaceProductionActivity
from logistics_app.forms import (
    InternalPackageForm,
    PackageItemFormSet,
    PackageReceptionForm,
    ShipmentTripForm,
    TripStopFormSet,
)
from logistics_app.models import (
    Package,
    PackageEventLog,
    PackageImage,
    PackageItem,
    ShipmentTrip,
    TripStop,
)
from logistics_app.services import (
    PackageService,
    PackageSheetGenerator,
    ShipmentTripService,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# УПРАВЛЕНИЕ РЕЙСАМИ МАШИН НА МПД
# ==============================================================================

class ShipmentTripListView(LoginRequiredMixin, ListView):
    """Реестр рейсов автотранспорта на МПД с фильтрацией по статусам и поиском."""

    model = ShipmentTrip
    template_name = "logistics_app/trip_list.html"
    context_object_name = "trips"
    paginate_by = 15

    def get_queryset(self) -> QuerySet[ShipmentTrip]:
        """Возвращает оптимизированный список рейсов с учетом активной вкладки и поискового запроса.

        Returns:
            QuerySet[ShipmentTrip]: Отфильтрованный набор рейсов.
        """
        qs = (
            ShipmentTrip.objects.select_related("dispatcher", "driver_user", "origin_point")
            .prefetch_related("stops__mpd", "packages")
            .annotate(packages_total=Count("packages", distinct=True))
        )

        tab = self.request.GET.get("tab", "active")
        if tab == "active":
            qs = qs.filter(
                status__in=[
                    ShipmentTrip.Status.PLANNING,
                    ShipmentTrip.Status.CONSOLIDATED,
                    ShipmentTrip.Status.IN_TRANSIT,
                    ShipmentTrip.Status.ARRIVED,
                ]
            )
        elif tab == "planning":
            qs = qs.filter(status=ShipmentTrip.Status.PLANNING)
        elif tab == "in_transit":
            qs = qs.filter(status__in=[ShipmentTrip.Status.IN_TRANSIT, ShipmentTrip.Status.ARRIVED])
        elif tab == "completed":
            qs = qs.filter(status__in=[ShipmentTrip.Status.COMPLETED, ShipmentTrip.Status.CANCELLED])

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            qs = qs.filter(
                Q(trip_number__icontains=search_query)
                | Q(driver_name__icontains=search_query)
                | Q(vehicle_model__icontains=search_query)
                | Q(vehicle_reg_number__icontains=search_query)
                | Q(stops__mpd__name__icontains=search_query)
                | Q(comment__icontains=search_query)
            ).distinct()

        return qs.order_by("-planned_date", "-created_at")

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует расширенный контекст со счетчиками статусов и ожидающих посылок.

        Returns:
            Dict[str, Any]: Контекст шаблона реестра рейсов.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = "Рейсы и отправка машин на МПД"
        context["active_tab"] = self.request.GET.get("tab", "active")
        context["search_query"] = self.request.GET.get("q", "")

        # Счетчики
        all_trips = ShipmentTrip.objects.all()
        context["count_all"] = all_trips.count()
        context["count_active"] = all_trips.filter(
            status__in=[
                ShipmentTrip.Status.PLANNING,
                ShipmentTrip.Status.CONSOLIDATED,
                ShipmentTrip.Status.IN_TRANSIT,
                ShipmentTrip.Status.ARRIVED,
            ]
        ).count()
        context["count_planning"] = all_trips.filter(status=ShipmentTrip.Status.PLANNING).count()
        context["count_in_transit"] = all_trips.filter(
            status__in=[ShipmentTrip.Status.IN_TRANSIT, ShipmentTrip.Status.ARRIVED]
        ).count()
        context["count_completed"] = all_trips.filter(
            status__in=[ShipmentTrip.Status.COMPLETED, ShipmentTrip.Status.CANCELLED]
        ).count()

        # Пул посылок, ожидающих назначения в рейс
        context["pending_packages_count"] = Package.objects.filter(
            status=Package.Status.AWAITING_SHIPMENT
        ).count()

        return context


class ShipmentTripCreateView(LoginRequiredMixin, CreateView):
    """Формирование новой заявки на рейс машины с промежуточными МПД."""

    model = ShipmentTrip
    form_class = ShipmentTripForm
    template_name = "logistics_app/trip_form.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет промежуточных остановок МПД в контекст.

        Returns:
            Dict[str, Any]: Контекст шаблона создания рейса.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = "Формирование заявки на рейс машины"
        if self.request.POST:
            context["stops_formset"] = TripStopFormSet(self.request.POST)
        else:
            context["stops_formset"] = TripStopFormSet()
        return context

    def form_valid(self, form: ShipmentTripForm) -> HttpResponse:
        """Валидирует и сохраняет рейс с остановками в рамках единой транзакции.

        Args:
            form (ShipmentTripForm): Заполненная форма рейса.

        Returns:
            HttpResponse: Редирект на карточку созданного рейса.
        """
        context = self.get_context_data()
        stops_formset = context["stops_formset"]

        if stops_formset.is_valid():
            with transaction.atomic():
                form.instance.dispatcher = self.request.user
                trip = form.save()
                stops_formset.instance = trip
                stops_formset.save()

            messages.success(
                self.request,
                f"Заявка на рейс № {trip.trip_number} успешно сформирована. Укажите посылки для отправки.",
            )
            return redirect("logistics_app:trip_detail", pk=trip.pk)

        return self.render_to_response(self.get_context_data(form=form))


class ShipmentTripUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование параметров рейса и маршрута заезда."""

    model = ShipmentTrip
    form_class = ShipmentTripForm
    template_name = "logistics_app/trip_form.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет остановок в контекст редактирования.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = f"Редактирование рейса № {self.object.trip_number}"
        if self.request.POST:
            context["stops_formset"] = TripStopFormSet(self.request.POST, instance=self.object)
        else:
            context["stops_formset"] = TripStopFormSet(instance=self.object)
        return context

    def form_valid(self, form: ShipmentTripForm) -> HttpResponse:
        """Сохраняет обновленные данные рейса и промежуточных остановок.

        Args:
            form (ShipmentTripForm): Заполненная форма.

        Returns:
            HttpResponse: Редирект на детальный просмотр рейса.
        """
        context = self.get_context_data()
        stops_formset = context["stops_formset"]

        if stops_formset.is_valid():
            with transaction.atomic():
                trip = form.save()
                stops_formset.save()

            messages.success(self.request, f"Параметры рейса № {trip.trip_number} успешно обновлены.")
            return redirect("logistics_app:trip_detail", pk=trip.pk)

        return self.render_to_response(self.get_context_data(form=form))


class ShipmentTripDetailView(LoginRequiredMixin, DetailView):
    """Детальный просмотр рейса машины: маршрут, список посылок и управление отправкой."""

    model = ShipmentTrip
    template_name = "logistics_app/trip_detail.html"
    context_object_name = "trip"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует контекст детального просмотра со списком остановок и прикрепленных посылок.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        trip: ShipmentTrip = self.object

        context["title"] = f"Рейс № {trip.trip_number} — {trip.planned_date.strftime('%d.%m.%Y')}"
        context["stops"] = trip.stops.select_related("mpd").order_by("stop_order")
        context["packages"] = (
            trip.packages.select_related("origin", "destination", "sender", "recipient", "received_by")
            .prefetch_related("items", "photos")
            .order_by("-urgency", "destination__name")
        )

        # Доступные для прикрепления посылки из очереди
        context["available_packages"] = Package.objects.filter(
            status=Package.Status.AWAITING_SHIPMENT
        ).select_related("origin", "destination", "sender")

        # Итоговая статистика по грузу
        packages_list = list(context["packages"])
        context["total_weight"] = sum(
            (pkg.weight_kg for pkg in packages_list if pkg.weight_kg is not None), Decimal("0")
        )
        context["total_places"] = sum(pkg.places_count for pkg in packages_list)
        context["total_items_count"] = sum(pkg.items.count() for pkg in packages_list)

        return context


class ShipmentTripActionView(LoginRequiredMixin, View):
    """Обработчик действий над рейсом: консолидация, выезд, прибытие на МПД, завершение, отмена."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Выполняет перевод статуса рейса и сопутствующих посылок.

        Args:
            request (HttpRequest): Входящий HTTP-запрос.
            pk (int): Идентификатор рейса.

        Returns:
            HttpResponse: Редирект на детальную страницу рейса.
        """
        trip = get_object_or_404(ShipmentTrip, pk=pk)
        action = request.POST.get("action", "").strip()

        try:
            if action == "consolidate":
                ShipmentTripService.consolidate_trip(trip, request.user)
                messages.success(
                    request,
                    f"Рейс № {trip.trip_number} скомплектован. Прием заявок закрыт, машина готова к погрузке.",
                )

            elif action == "start":
                ShipmentTripService.start_trip(trip, request.user)
                messages.success(
                    request,
                    f"Рейс № {trip.trip_number} отправлен в путь! Все посылки ({trip.packages_count} шт.) переведены в статус «В пути».",
                )

            elif action == "arrive_stop":
                mpd_id = request.POST.get("mpd_id")
                if not mpd_id:
                    messages.error(request, "Не указан МПД прибытия.")
                    return redirect("logistics_app:trip_detail", pk=trip.pk)

                mpd = get_object_or_404(PlaceProductionActivity, pk=mpd_id)
                ShipmentTripService.arrive_at_stop(trip, mpd, request.user)
                messages.success(
                    request,
                    f"Зафиксировано прибытие машины на {mpd.name}. Грузы переданы сотрудникам для приемки.",
                )

            elif action == "complete":
                ShipmentTripService.complete_trip(trip, request.user)
                messages.success(request, f"Рейс № {trip.trip_number} успешно завершен.")

            elif action == "cancel":
                reason = request.POST.get("reason", "").strip()
                ShipmentTripService.cancel_trip(trip, request.user, reason=reason)
                messages.warning(
                    request,
                    f"Рейс № {trip.trip_number} отменен. Прикрепленные посылки возвращены в очередь ожидания отправки.",
                )

            else:
                messages.error(request, f"Неизвестное действие над рейсом: {action}")

        except Exception as exc:
            logger.exception("Ошибка при выполнении действия над рейсом %s: %s", trip.trip_number, exc)
            messages.error(request, f"Ошибка выполнения действия: {exc}")

        return redirect("logistics_app:trip_detail", pk=trip.pk)


# ==============================================================================
# УПРАВЛЕНИЕ ПОСЫЛКАМИ И ПРИЕМОЧНЫМ КОНТРОЛЕМ НА МПД
# ==============================================================================

class PackageListView(LoginRequiredMixin, ListView):
    """Реестр посылок с поддержкой серверной фильтрации, AJAX DataTables и вкладок."""

    model = Package
    template_name = "logistics_app/package_list.html"
    context_object_name = "packages"
    paginate_by = 15

    def get_queryset(self) -> QuerySet[Package]:
        """Возвращает оптимизированный queryset посылок с фильтрацией по статусу.

        Returns:
            QuerySet[Package]: Набор объектов Package.
        """
        qs = (
            Package.objects.select_related("origin", "destination", "sender", "recipient", "trip", "executor")
            .prefetch_related("items", "photos")
        )

        tab = self.request.GET.get("tab", "all")
        if tab == "queue":
            qs = qs.filter(status=Package.Status.AWAITING_SHIPMENT)
        elif tab == "in_transit":
            qs = qs.filter(status__in=[Package.Status.ASSIGNED_TO_TRIP, Package.Status.IN_TRANSIT])
        elif tab == "reception":
            qs = qs.filter(status=Package.Status.DELIVERED_AT_MPD)
        elif tab == "received":
            qs = qs.filter(status__in=[Package.Status.RECEIVED_FULL, Package.Status.RECEIVED_WITH_DISCREPANCY])
        elif tab == "discrepancy":
            qs = qs.filter(has_discrepancy=True)

        return qs.order_by("-created_at")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Обрабатывает стандартные GET-запросы и AJAX-вызовы DataTables.

        Args:
            request (HttpRequest): Входящий запрос.

        Returns:
            HttpResponse: HTML-страница или JSON-ответ DataTables.
        """
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            query = Q()
            search_list = [
                "date_of_dispatch",
                "number_of_dispatch",
                "track_number",
                "place_of_dispatch__name",
                "destination__name",
                "origin__name",
                "origin_custom",
                "executor__title",
                "sender__title",
                "recipient__title",
                "type_of_dispatch",
                "description",
            ]
            context = ajax_search(request, self, search_list, Package, query)
            return JsonResponse(context, safe=False)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует контекст реестра со статистикой по статусам посылок.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = "Реестр посылок и грузовых отправлений"
        context["active_tab"] = self.request.GET.get("tab", "all")

        # Счетчики
        all_pkgs = Package.objects.all()
        context["count_all"] = all_pkgs.count()
        context["count_queue"] = all_pkgs.filter(status=Package.Status.AWAITING_SHIPMENT).count()
        context["count_in_transit"] = all_pkgs.filter(
            status__in=[Package.Status.ASSIGNED_TO_TRIP, Package.Status.IN_TRANSIT]
        ).count()
        context["count_reception"] = all_pkgs.filter(status=Package.Status.DELIVERED_AT_MPD).count()
        context["count_received"] = all_pkgs.filter(
            status__in=[Package.Status.RECEIVED_FULL, Package.Status.RECEIVED_WITH_DISCREPANCY]
        ).count()
        context["count_discrepancy"] = all_pkgs.filter(has_discrepancy=True).count()

        # Активные рейсы для информационного блока
        context["active_trips"] = ShipmentTrip.objects.filter(
            status__in=[ShipmentTrip.Status.PLANNING, ShipmentTrip.Status.CONSOLIDATED]
        ).order_by("planned_date")[:5]

        return context


class PackageCreateView(LoginRequiredMixin, CreateView):
    """Оформление внутренней посылки на МПД с описью вложения."""

    model = Package
    form_class = InternalPackageForm
    template_name = "logistics_app/package_form.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет позиций описи в контекст создания посылки.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = "Оформление внутренней посылки на МПД"
        if self.request.POST:
            context["items_formset"] = PackageItemFormSet(self.request.POST)
        else:
            context["items_formset"] = PackageItemFormSet()

        # Список открытых рейсов для удобного выбора
        context["open_trips"] = ShipmentTrip.objects.filter(
            status__in=[ShipmentTrip.Status.PLANNING, ShipmentTrip.Status.CONSOLIDATED]
        ).order_by("planned_date")
        return context

    def form_valid(self, form: InternalPackageForm) -> HttpResponse:
        """Сохраняет посылку с позициями описи и фиксирует событие создания.

        Args:
            form (InternalPackageForm): Заполненная форма посылки.

        Returns:
            HttpResponse: Редирект на карточку созданной посылки.
        """
        context = self.get_context_data()
        items_formset = context["items_formset"]

        if items_formset.is_valid():
            with transaction.atomic():
                package = form.save(commit=False)
                package.sender = self.request.user
                profile = getattr(self.request.user, "user_work_profile", None)
                if profile and hasattr(profile, "divisions"):
                    try:
                        divisions = profile.divisions.all()
                        if divisions.exists():
                            package.sender_division = divisions.first()
                    except Exception:
                        pass

                # Устанавливаем статус
                if package.trip:
                    package.status = Package.Status.ASSIGNED_TO_TRIP
                else:
                    package.status = Package.Status.AWAITING_SHIPMENT

                package.save()
                items_formset.instance = package
                items_formset.save()

                # Запись в трекинг-журнал
                PackageEventLog.objects.create(
                    package=package,
                    event_type=PackageEventLog.EventType.CREATED,
                    user=self.request.user,
                    timestamp=timezone.now(),
                    message=f"Посылка оформлена отправителем. Направление: {package.origin_display} → {package.destination_display}.",
                    location=package.origin_display,
                )

                if package.trip:
                    PackageEventLog.objects.create(
                        package=package,
                        event_type=PackageEventLog.EventType.ATTACHED_TO_TRIP,
                        user=self.request.user,
                        timestamp=timezone.now(),
                        message=f"Посылка привязана к рейсу {package.trip.trip_number} (выезд {package.trip.planned_date.strftime('%d.%m.%Y')}).",
                        location=package.origin_display,
                    )

            messages.success(
                self.request,
                f"Посылка {package.track_number} успешно зарегистрирована. Распечатайте опись вложения.",
            )
            return redirect("logistics_app:package_detail", pk=package.pk)

        return self.render_to_response(self.get_context_data(form=form))


class PackageUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование посылки и описи вложения до момента отправки."""

    model = Package
    form_class = InternalPackageForm
    template_name = "logistics_app/package_form.html"

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Ограничивает возможность редактирования только неотправленными посылками.

        Args:
            request (HttpRequest): Запрос.

        Returns:
            HttpResponse: Страница или редирект.
        """
        package = self.get_object()
        if package.status in [
            Package.Status.IN_TRANSIT,
            Package.Status.DELIVERED_AT_MPD,
            Package.Status.RECEIVED_FULL,
            Package.Status.RECEIVED_WITH_DISCREPANCY,
        ]:
            messages.warning(
                request,
                f"Посылка {package.track_number} находится в статусе «{package.get_status_display()}» и не подлежит редактированию.",
            )
            return redirect("logistics_app:package_detail", pk=package.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Добавляет формсет описи вложения в контекст редактирования.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        context["title"] = f"Редактирование посылки {self.object.track_number}"
        if self.request.POST:
            context["items_formset"] = PackageItemFormSet(self.request.POST, instance=self.object)
        else:
            context["items_formset"] = PackageItemFormSet(instance=self.object)
        return context

    def form_valid(self, form: InternalPackageForm) -> HttpResponse:
        """Сохраняет отредактированную посылку и позиции описи.

        Args:
            form (InternalPackageForm): Заполненная форма.

        Returns:
            HttpResponse: Редирект на детальный просмотр посылки.
        """
        context = self.get_context_data()
        items_formset = context["items_formset"]

        if items_formset.is_valid():
            with transaction.atomic():
                package = form.save()
                items_formset.save()

            messages.success(self.request, f"Посылка {package.track_number} успешно обновлена.")
            return redirect("logistics_app:package_detail", pk=package.pk)

        return self.render_to_response(self.get_context_data(form=form))


class PackageDetailView(LoginRequiredMixin, DetailView):
    """Детальный просмотр посылки: статус, опись вложения, фотографии и таймлайн трекинга."""

    model = Package
    template_name = "logistics_app/package_detail.html"
    context_object_name = "package"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Формирует расширенный контекст карточки посылки.

        Returns:
            Dict[str, Any]: Контекст шаблона.
        """
        context = super().get_context_data(**kwargs)
        package: Package = self.object

        context["title"] = f"Посылка {package.track_number} → {package.destination_display}"
        context["items"] = package.items.all().order_by("item_order")
        context["photos_shipment"] = package.photos.filter(stage=PackageImage.Stage.SHIPMENT)
        context["photos_reception"] = package.photos.filter(stage=PackageImage.Stage.RECEPTION)
        context["event_logs"] = package.event_logs.select_related("user").order_by("-timestamp")

        # Открытые рейсы для быстрого прикрепления из карточки
        context["available_trips"] = ShipmentTrip.objects.filter(
            status__in=[ShipmentTrip.Status.PLANNING, ShipmentTrip.Status.CONSOLIDATED]
        ).order_by("planned_date")

        # Возможность приемки
        context["can_receive"] = package.status in [
            Package.Status.IN_TRANSIT,
            Package.Status.DELIVERED_AT_MPD,
        ]

        return context


class PackageReceiveView(LoginRequiredMixin, View):
    """Мобильный экран приемочного контроля на МПД: поштучная сверка и фотофиксация."""

    template_name = "logistics_app/package_receive.html"

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Отображает мобильную форму поштучной приемки позиций посылки.

        Args:
            request (HttpRequest): Запрос.
            pk (int): Идентификатор посылки.

        Returns:
            HttpResponse: Страница приемки груза.
        """
        package = get_object_or_404(
            Package.objects.select_related("origin", "destination", "sender", "trip").prefetch_related("items"),
            pk=pk,
        )

        form = PackageReceptionForm()
        items = package.items.all().order_by("item_order")

        return render(
            request,
            self.template_name,
            {
                "package": package,
                "items": items,
                "form": form,
                "title": f"Приемка посылки {package.track_number} на {package.destination_display}",
            },
        )

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Выполняет обработку результатов приемочного контроля с МПД.

        Args:
            request (HttpRequest): Входящий запрос с данными сверки и файлами фото.
            pk (int): Идентификатор принимаемой посылки.

        Returns:
            HttpResponse: Редирект на карточку посылки с выводом итогового статуса.
        """
        package = get_object_or_404(
            Package.objects.select_related("destination", "origin").prefetch_related("items"),
            pk=pk,
        )

        reception_comment = request.POST.get("reception_comment", "").strip()
        photos = request.FILES.getlist("photos")

        # Собираем сверку по каждой позиции
        items_reception: List[Dict[str, Any]] = []
        for item in package.items.all():
            qty_val = request.POST.get(f"qty_rec_{item.id}")
            status_val = request.POST.get(f"status_{item.id}", PackageItem.ItemStatus.ACCEPTED)
            comment_val = request.POST.get(f"comment_{item.id}", "").strip()

            items_reception.append(
                {
                    "id": item.id,
                    "quantity_received": qty_val,
                    "item_status": status_val,
                    "discrepancy_comment": comment_val,
                }
            )

        try:
            received_pkg = PackageService.receive_package_on_mpd(
                package=package,
                user=request.user,
                items_reception=items_reception,
                photos=photos,
                reception_comment=reception_comment,
            )

            if received_pkg.has_discrepancy:
                messages.warning(
                    request,
                    f"Посылка {received_pkg.track_number} принята С РАСХОЖДЕНИЯМИ. Зафиксированы замечания или недостача.",
                )
            else:
                messages.success(
                    request,
                    f"Посылка {received_pkg.track_number} успешно принята в полном объеме без замечаний!",
                )

        except Exception as exc:
            logger.exception("Ошибка при приемке посылки %s: %s", package.track_number, exc)
            messages.error(request, f"Ошибка при сохранении результатов приемки: {exc}")
            return redirect("logistics_app:package_receive", pk=package.pk)

        return redirect("logistics_app:package_detail", pk=package.pk)


class PackageAttachTripView(LoginRequiredMixin, View):
    """Прикрепление посылки к выбранному рейсу машины."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Прикрепляет посылку к рейсу.

        Args:
            request (HttpRequest): Запрос с ID рейса.
            pk (int): Идентификатор посылки.

        Returns:
            HttpResponse: Редирект обратно.
        """
        package = get_object_or_404(Package, pk=pk)
        trip_id = request.POST.get("trip_id")

        if not trip_id:
            messages.error(request, "Не указан рейс для назначения.")
            return redirect("logistics_app:package_detail", pk=package.pk)

        trip = get_object_or_404(ShipmentTrip, pk=trip_id)

        try:
            PackageService.attach_to_trip(package=package, trip=trip, user=request.user)
            messages.success(
                request,
                f"Посылка {package.track_number} включена в рейс № {trip.trip_number} (выезд {trip.planned_date.strftime('%d.%m.%Y')}).",
            )
        except Exception as exc:
            messages.error(request, f"Ошибка привязки к рейсу: {exc}")

        # Возвращаемся на реферер или карточку посылки
        next_url = request.POST.get("next") or reverse("logistics_app:package_detail", kwargs={"pk": package.pk})
        return HttpResponseRedirect(next_url)


class PackageDetachTripView(LoginRequiredMixin, View):
    """Исключение посылки из рейса и возврат в очередь ожидания."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Исключает посылку из рейса.

        Args:
            request (HttpRequest): Запрос.
            pk (int): Идентификатор посылки.

        Returns:
            HttpResponse: Редирект.
        """
        package = get_object_or_404(Package, pk=pk)
        reason = request.POST.get("reason", "").strip()

        try:
            PackageService.detach_from_trip(package=package, user=request.user, reason=reason)
            messages.info(request, f"Посылка {package.track_number} исключена из рейса и возвращена в очередь.")
        except Exception as exc:
            messages.error(request, f"Ошибка исключения из рейса: {exc}")

        next_url = request.POST.get("next") or reverse("logistics_app:package_detail", kwargs={"pk": package.pk})
        return HttpResponseRedirect(next_url)


class PackageSheetPdfView(LoginRequiredMixin, View):
    """Генерация и отдача печатной формы «Опись вложения и накладная передачи груза» (PDF)."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        """Генерирует PDF-документ с QR-кодом для сопроводительной описи.

        Args:
            request (HttpRequest): Запрос.
            pk (int): Идентификатор посылки.

        Returns:
            HttpResponse: Сгенерированный PDF-файл.
        """
        package = get_object_or_404(
            Package.objects.select_related(
                "origin",
                "destination",
                "sender",
                "recipient",
                "trip",
                "trip__driver_user",
            ).prefetch_related("items"),
            pk=pk,
        )

        try:
            pdf_bytes = PackageSheetGenerator.generate_pdf(package)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            filename = f"Package_{package.track_number or package.pk}.pdf"
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response
        except Exception as exc:
            logger.exception("Ошибка при генерации описи вложения для посылки %s: %s", package.track_number, exc)
            messages.error(request, f"Не удалось сформировать печатную форму: {exc}")
            return redirect("logistics_app:package_detail", pk=package.pk)
