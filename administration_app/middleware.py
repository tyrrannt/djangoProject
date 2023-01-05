import time
from contracts_app.models import Contract


def timing(get_response):
    def middleware(request):
        # t1 = time.time()
        response = get_response(request)
        # t2 = time.time()
        # total_time = (t2 - t1)
        # print(total_time)
        return response

    return middleware

