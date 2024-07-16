import sublime
import sublime_plugin
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import json
import functools
import html

POGODASTATUSBAR_SETTING_FILE = 'PogodaStatusBar.sublime-settings'


class PogodaStatusBar(sublime_plugin.EventListener):
    # https://www.gismeteo.ru/api
    # Weather icons
    _icons = {
        "🌞": {"d"},
        "🌙": {"n"},
        "☁️": {"n", "c"},
        "🌧": {"rs", "c", "r"},
        "🌤": {"d", "c"},
        "🌦": {"d", "r"},
        "🌩️": {"c", "st"},
        "⛈️": {"c", "st", "r"},
        "🌨": {"c", "s"},
        "💨": {"mist"},
        "⚡️": {"st"},
    }

    # Traffic level icons
    _ticons = {'green': '🟢', 'yellow': '🟡', 'red': '🔴'}

    # Settings: update interval
    _updateInterval = None
    # Settings: output template
    _template = None
    # Settings: current region
    _region = None
    # Cache of statusbar string
    _status = None
    # Was plugin started
    _activated = False
    # Current view (Sublime's object)
    _view = None

    def on_activated_async(self, view):
        self._run(view)

    # Run for given window (view)
    def _run(self, view):
        self._view = view

        if not self._activated:
            settings = sublime.load_settings(POGODASTATUSBAR_SETTING_FILE)
            self._updateInterval = settings.get('update_interval', 600)
            self._template = settings.get('template', None)
            self._region = self._getRegionData()
            self._updateData()
            self._startTimer()

            self._activated = True

        self._showStatus()

    # Get current region data
    @functools.cache
    def _getRegionData(self):
        try:
            url = "https://yandex.ru/tune/geo/"
            content = urllib.request.urlopen(url).read().decode('utf-8')
            region_data = re.search(r'data-bem="([^"]+coords[^"]+)"', str(content)).group(1)
            parsed_region_data = json.loads(html.unescape(region_data))

            # {'id': xx, 'region': 'XXXXX', 'coords': ['XX.XXXXX', 'XX.XXXXX'], 'accuracy': 'XXXXXX'}
            return parsed_region_data['checkbox']['auto']
        except (IOError, AttributeError):
            return None

    # Timer loop
    def _startTimer(self):
        if self._updateData():
            self._showStatus()
            timeout = self._updateInterval
        else:
            # if failed retry in minite
            timeout = 60

        sublime.set_timeout_async(lambda: self._startTimer(), timeout * 1e3)

    # Get current traffic level
    def _getData(self):
        try:
            url = "https://export.yandex.ru/bar/reginfo.xml?region=" + str(self._region['id'])
            content = urllib.request.urlopen(url).read()
            return ET.fromstring(content)
        except (IOError, ET.ParseError):
            return None

    # Get weather Unicode icon
    def _getStatus(self, coded_weather):
        codes = {x.strip("0123456789") for x in coded_weather.split(".")}

        max_icon = None
        max_score = 0

        for icon, code in self._icons.items():
            result = codes & code
            score = sum(len(x) for x in result)
            if score > max_score:
                max_icon, max_score = icon, score

        return max_icon

    # Get traffic level icon from XML element
    def _getTrafficIcon(self, el):
        return self._ticons[el.find('icon').text]

    # Get Gismeteo region by city coords
    @functools.cache
    def _getGismeteoRegion(self, coords):
        url = 'https://services.gismeteo.net/inform-service/inf_chrome/cities/?lng=%s&lat=%s&count=1&lang=en'
        content = urllib.request.urlopen(url % coords).read().decode('utf-8')

        return ET.fromstring(content).find('item').attrib['id']

    # Get Gistemeto forecast data
    def _getGismeteoForecast(self, region):
        try:
            url = 'https://services.gismeteo.ru/inform-service/inf_chrome/forecast/?lang=en&city=%s' % region
            content = urllib.request.urlopen(url).read()
            return ET.fromstring(content)
        except (IOError, ET.ParseError):
            return None


    # Update statusbar string cache
    def _updateData(self):
        xml = self._getData()

        if xml is not None:
            title = xml.find('region').find('title').text
            gm_xml = self._getGismeteoForecast(self._getGismeteoRegion(tuple(self._region['coords'])))

            weather = gm_xml.findall('./location/fact/values')[0]
            status = self._getStatus(weather.attrib['icon'])
            temp = weather.attrib['t']

            try:
                traffic = xml.find('traffic').find('region')
                tlevel = traffic.find('level').text
                ticon = self._getTrafficIcon(traffic)
            except AttributeError:
                tlevel, ticon = '', ''

            self._status = self._template % vars()
            return True
        else:
            self._status = None
            return False

    # Print cached status in current view
    def _showStatus(self):
        if self._status is not None:
            self._view.set_status('YandexPogoda', self._status)
