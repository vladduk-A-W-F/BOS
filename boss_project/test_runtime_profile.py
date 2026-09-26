"""The runtime badge must identify the real profile without promoting demo KPIs."""
from django.test import SimpleTestCase, RequestFactory, override_settings
import json
from boss_project.refinement_views import runtime_status
from boss_project.version import VERSION


class A09RuntimeProfileTests(SimpleTestCase):
    @override_settings(WSGI_APPLICATION='boss_project.server_wsgi.application', BOS_DATA_MODE='working')
    def test_server_profile_is_explicit_and_demo_metrics_stay_labelled(self):
        value = json.loads(runtime_status(RequestFactory().get('/api/runtime/status/')).content)
        self.assertEqual(value['mode'], 'server')
        self.assertEqual(value['data_mode'], 'working')
        self.assertEqual(value['version'], VERSION)
        self.assertEqual(value['dashboard'], 'demo_generated')
        self.assertEqual(value['organizer'], 'browser_local')

    @override_settings(WSGI_APPLICATION='boss_project.wsgi.application', BOS_DATA_MODE='demo')
    def test_local_profile_keeps_its_actual_mode(self):
        value = json.loads(runtime_status(RequestFactory().get('/api/runtime/status/')).content)
        self.assertEqual(value['mode'], 'local')
        self.assertEqual(value['data_mode'], 'demo')
