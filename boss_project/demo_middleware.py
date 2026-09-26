from django.conf import settings
from django.http import JsonResponse

class LocalDemoGuard:
    """The supplied demonstration is intentionally restricted to local access."""
    def __init__(self,get_response):
        self.get_response=get_response
    def __call__(self,request):
        if request.META.get('REMOTE_ADDR') not in ('127.0.0.1','::1'):
            return JsonResponse({'error':'Демонстрація доступна лише локально.'},status=403)
        from boss_project.import_request_body import capture_import_body
        rejected = capture_import_body(request)
        if rejected is not None:
            return rejected
        return self.get_response(request)
