# middleware.py
from django.shortcuts import redirect
from django.urls import reverse

class LockScreenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get('locked', False) and not request.path.startswith(reverse('customers_app:lock_screen')):
            return redirect('customers_app:lock_screen')
        return self.get_response(request)
