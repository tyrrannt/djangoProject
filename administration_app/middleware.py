import time
from contracts_app.models import Contract


def timing(get_response):
    def middleware(request):
        t1 = time.time()
        response = get_response(request)
        t2 = time.time()
        print("TOTAL TIME:", (t2 - t1))
        return response

    return middleware
