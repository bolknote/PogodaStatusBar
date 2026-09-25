import sublime
import sublime_plugin
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import functools
import sys
from typing import Any, Dict, Optional, Set, Tuple

POGODASTATUSBAR_SETTING_FILE = 'PogodaStatusBar.sublime-settings'


class PogodaStatusBar(sublime_plugin.EventListener):
    _requestTimeout: int = 5
    _reginfoCacheTtlSeconds: int = 300
    _reginfoCacheValue: Optional[ET.Element] = None
    _reginfoCacheUntil: float = 0.0

    # https://www.gismeteo.ru/api
    # Weather icons
    _icons: Dict[str, Set[str]] = {
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
    _ticons: Dict[str, str] = {'green': '🟢', 'yellow': '🟡', 'red': '🔴'}

    # Settings: update interval
    _updateInterval: Optional[int] = None
    # Settings: output template
    _template: Optional[str] = None
    # Last known coordinates from reginfo.xml
    _region: Optional[Tuple[str, str]] = None
    # Cache of statusbar string
    _status: Optional[str] = None
    # Was plugin started
    _activated: bool = False
    # Current view (Sublime's object)
    _view: Optional[sublime.View] = None
    # Cache decorator
    _cache: Any = functools.lru_cache(maxsize=None) if sys.version_info < (3, 9, 0) else functools.cache

    def on_activated_async(self, view: sublime.View) -> None:
        self._run(view)

    # Run for given window (view)
    def _run(self, view: sublime.View) -> None:
        self._view = view

        if not self._activated:
            settings = sublime.load_settings(POGODASTATUSBAR_SETTING_FILE)
            self._updateInterval = settings.get('update_interval', 600)
            self._template = settings.get('template', None)

            # Mark the listener as active before starting the timer.  The timer
            # schedules its own retry even when the first update fails.
            self._activated = True
            self._startTimer()
        else:
            self._showStatus()

    # Get current region data
    @staticmethod
    def _getRegionData(xml: ET.Element) -> Tuple[str, str]:
        # Coordinates format for upstream XML can vary, so we check several known forms.
        candidates = (
            ('lat', 'lon'),
            ('lat', 'lng'),
            ('latitude', 'longitude'),
        )

        for el in xml.iter():
            attrs = {k.lower(): v for k, v in el.attrib.items()}
            for lat_key, lon_key in candidates:
                if lat_key in attrs and lon_key in attrs:
                    float(attrs[lat_key])
                    float(attrs[lon_key])
                    return attrs[lon_key], attrs[lat_key]

            text = (el.text or '').strip()
            if text:
                parts = [x.strip() for x in text.split(',')]
                if len(parts) == 2:
                    float(parts[0])
                    float(parts[1])
                    return parts[0], parts[1]

        raise AttributeError('Coordinates not found in reginfo.xml')

    # Timer loop
    def _startTimer(self) -> None:
        # Retry failures after a minute.  Scheduling in finally keeps one
        # unexpected exception from stopping the refresh loop permanently.
        timeout = 60

        try:
            if self._updateData():
                self._showStatus()
                timeout = self._updateInterval
        finally:
            sublime.set_timeout_async(lambda: self._startTimer(), timeout * 1e3)

    # Get current traffic level
    def _getData(self) -> Optional[ET.Element]:
        now = time.monotonic()
        if self._reginfoCacheValue is not None and now < self._reginfoCacheUntil:
            return self._reginfoCacheValue

        try:
            url = "https://export.yandex.ru/bar/reginfo.xml"
            content = urllib.request.urlopen(url, timeout=self._requestTimeout).read()
            xml = ET.fromstring(content)
            self._reginfoCacheValue = xml
            self._reginfoCacheUntil = now + self._reginfoCacheTtlSeconds
            return xml
        except (IOError, urllib.error.URLError, TimeoutError, ET.ParseError):
            return None

    # Get weather Unicode icon
    def _getStatus(self, coded_weather: str) -> Optional[str]:
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
    def _getTrafficIcon(self, el: ET.Element) -> str:
        return self._ticons[el.find('icon').text]

    # Get Gismeteo region by city coords
    @staticmethod
    @_cache
    def _getGismeteoRegion(coords: Tuple[str, str]) -> str:
        url = 'https://services.gismeteo.net/inform-service/inf_chrome/cities/?lng=%s&lat=%s&count=1&lang=en'
        content = urllib.request.urlopen(
            url % coords,
            timeout=PogodaStatusBar._requestTimeout,
        ).read().decode('utf-8')

        return ET.fromstring(content).find('item').attrib['id']

    # Get Gistemeto forecast data
    def _getGismeteoForecast(self, region: str) -> Optional[ET.Element]:
        try:
            url = 'https://services.gismeteo.ru/inform-service/inf_chrome/forecast/?lang=en&city=%s' % region
            content = urllib.request.urlopen(url, timeout=self._requestTimeout).read()
            return ET.fromstring(content)
        except (IOError, urllib.error.URLError, TimeoutError, ET.ParseError):
            return None


    # Update statusbar string cache
    def _updateData(self) -> bool:
        xml = self._getData()

        if xml is None:
            self._status = None
            return False

        try:
            region = self._getRegionData(xml)
            title = xml.find('region').find('title').text
            gm_xml = self._getGismeteoForecast(self._getGismeteoRegion(region))
            weather = gm_xml.findall('./location/fact/values')[0]
            status = self._getStatus(weather.attrib['icon'])
            temp = weather.attrib['t']
        except (AttributeError, IndexError, KeyError, OSError, TypeError,
                ValueError, ET.ParseError):
            self._status = None
            return False

        self._region = region

        try:
            traffic = xml.find('traffic').find('region')
            tlevel = traffic.find('level').text
            ticon = self._getTrafficIcon(traffic)
        except AttributeError:
            tlevel, ticon = '', ''

        self._status = self._template % vars()
        return True

    # Print cached status in current view
    def _showStatus(self) -> None:
        if self._status is not None:
            self._view.set_status('YandexPogoda', self._status)
