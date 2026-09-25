import importlib
import sys
import types
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from unittest import mock


class FakeEventListener:
    pass


class FakeSettings:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, name, default=None):
        return self.values.get(name, default)


class FakeView:
    def __init__(self):
        self.statuses = []

    def set_status(self, key, value):
        self.statuses.append((key, value))


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def read(self):
        return self.content


scheduled = []
settings = FakeSettings({
    'update_interval': 600,
    'template': '%(title)s|%(temp)s|%(status)s|%(tlevel)s|%(ticon)s',
})

fake_sublime = types.ModuleType('sublime')
fake_sublime.View = FakeView
fake_sublime.load_settings = lambda _: settings
fake_sublime.set_timeout_async = (
    lambda callback, timeout: scheduled.append((callback, timeout))
)

fake_sublime_plugin = types.ModuleType('sublime_plugin')
fake_sublime_plugin.EventListener = FakeEventListener

sys.modules['sublime'] = fake_sublime
sys.modules['sublime_plugin'] = fake_sublime_plugin

PogodaStatusBar = importlib.import_module('PogodaStatusBar')


class PogodaStatusBarTimerTest(unittest.TestCase):
    reginfo = ET.fromstring('''
        <info>
            <region>
                <title>Test city</title>
                <point lat="55.75" lon="37.61" />
            </region>
            <traffic>
                <region>
                    <level>3</level>
                    <icon>green</icon>
                </region>
            </traffic>
        </info>
    ''')

    def setUp(self):
        scheduled.clear()
        PogodaStatusBar.PogodaStatusBar._getGismeteoRegion.cache_clear()

    def new_listener(self):
        listener = PogodaStatusBar.PogodaStatusBar()
        listener._activated = False
        listener._reginfoCacheValue = None
        listener._reginfoCacheUntil = 0.0
        return listener

    def test_gismeteo_region_network_error_is_retried(self):
        listener = self.new_listener()
        listener._getData = lambda: self.reginfo
        view = FakeView()

        calls = 0

        def urlopen(url, timeout):
            nonlocal calls
            calls += 1

            if calls == 1:
                raise urllib.error.URLError('temporary DNS failure')
            if '/cities/' in url:
                return FakeResponse(b'<cities><item id="123" /></cities>')
            if '/forecast/' in url:
                return FakeResponse(
                    b'<forecast><location><fact>'
                    b'<values icon="d" t="20" />'
                    b'</fact></location></forecast>'
                )
            self.fail('Unexpected URL: %s' % url)

        with mock.patch.object(
                PogodaStatusBar.urllib.request, 'urlopen', side_effect=urlopen):
            listener._run(view)

            self.assertTrue(listener._activated)
            self.assertEqual(len(scheduled), 1)
            retry, timeout = scheduled.pop()
            self.assertEqual(timeout, 60 * 1000)
            self.assertEqual(view.statuses, [])

            retry()

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][1], 600 * 1000)
        self.assertEqual(
            view.statuses,
            [('YandexPogoda', 'Test city|20|🌞|3|🟢')],
        )

    def test_first_yandex_failure_starts_retry(self):
        listener = self.new_listener()
        listener._getData = lambda: None

        listener._run(FakeView())

        self.assertTrue(listener._activated)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][1], 60 * 1000)

    def test_unexpected_exception_does_not_stop_timer(self):
        listener = self.new_listener()
        listener._updateData = mock.Mock(side_effect=RuntimeError('bad data'))

        with self.assertRaisesRegex(RuntimeError, 'bad data'):
            listener._startTimer()

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0][1], 60 * 1000)


if __name__ == '__main__':
    unittest.main()
