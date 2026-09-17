"""The B02 stream boundary, before multipart/CSRF parsing; no network framing claims."""
import io
from django.test import SimpleTestCase,RequestFactory,override_settings
from boss_project.import_request_body import MAX_BODY,capture_import_body
from boss_project.demo_middleware import LocalDemoGuard
from boss_project.server_config import TrustedProxyMiddleware
from erp.import_views import read_input


class ImportBodyBoundaryTests(SimpleTestCase):
    def stream(self,body,declared):
        class Tracked(io.BytesIO):
            def read(self,size=-1):self.requested.append(size);return super().read(size)
        request=RequestFactory().post('/api/erp/import/preview/',b'{}',content_type='application/json')
        stream=Tracked(body);stream.requested=[];request._stream=stream
        if declared is None:request.META.pop('CONTENT_LENGTH',None)
        else:request.META['CONTENT_LENGTH']=declared
        return request,stream

    def test_missing_or_forged_length_reads_at_most_limit_plus_one_before_parser(self):
        for declared in (None,'1'):
            request,stream=self.stream(b'x'*(MAX_BODY+1000),declared)
            response=capture_import_body(request)
            self.assertEqual(response.status_code,413)
            self.assertEqual(stream.requested,[MAX_BODY+1]);self.assertEqual(stream.tell(),MAX_BODY+1)
            self.assertFalse(hasattr(request,'_post'));self.assertFalse(hasattr(request,'_files'))
        request,stream=self.stream(b'{}','1')
        self.assertEqual(capture_import_body(request).status_code,400)
        request,stream=self.stream(b'{}',None)
        self.assertIsNone(capture_import_body(request));value,_,_=read_input(request);self.assertEqual(value,{})
        self.assertEqual(stream.requested,[MAX_BODY+1])

    @override_settings(BOS_TRUSTED_PROXY_IPS=['127.0.0.1','::1'])
    def test_local_and_server_hooks_reject_before_downstream_parsing(self):
        for middleware in (LocalDemoGuard,TrustedProxyMiddleware):
            request,stream=self.stream(b'x'*(MAX_BODY+2),None)
            request.META.update(REMOTE_ADDR='127.0.0.1',HTTP_X_FORWARDED_PROTO='https',HTTP_X_FORWARDED_FOR='127.0.0.1')
            called=[];response=middleware(lambda r:called.append(r.POST))(request)
            self.assertEqual(called,[]);self.assertEqual(response.status_code,413);self.assertEqual(stream.requested,[MAX_BODY+1])
