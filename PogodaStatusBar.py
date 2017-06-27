import sublime
import sublime_plugin
import urllib
import xml.etree.ElementTree as ET

POGODASTATUSBAR_SETTING_FILE = 'PogodaStatusBar.sublime-settings'


class PogodaStatusBar(sublime_plugin.EventListener):
    # https://tech.yandex.ru/weather/doc/dg/concepts/translations-docpage/
    # Weather icons
    _icons = {
        "clear": "🌞",
        "mostly-clear": "🌤",
        "partly-cloudy": "🌤",
        "overcast": "🌥",
        "partly-cloudy-and-light-rain": "🌦",
        "partly-cloudy-and-rain": "🌧",
        "overcast-and-rain": "🌧",
        "overcast-thunderstorms-with-rain": "⛈",
        "cloudy": "🌤",
        "cloudy-and-light-rain": "🌦",
        "overcast-and-light-rain": "🌦",
        "cloudy-and-rain": "🌧",
        "overcast-and-wet-snow": "🌨",
        "partly-cloudy-and-light-snow": "🌨",
        "partly-cloudy-and-snow": "🌨",
        "overcast-and-snow": "🌨",
        "cloudy-and-light-snow": "🌨",
        "overcast-and-light-snow": "🌨",
        "cloudy-and-snow": "🌨"
    }

    # Traffic level icons
    _ticons = {'green': '🍏', 'yellow': '🍋', 'red': '🍅'}

    # Settings: update interval
    _updateInterval = None
    # Settings: output template
    _template = None
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

            self._updateData()
            self._startTimer()

            self._activated = True

        self._showStatus()

    # Timer loop
    def _startTimer(self):
        if self._updateData():
            self._showStatus()
            timeout = self._updateInterval
        else:
            # если не удалось обновить, попробовать через минуту
            timeout = 60

        sublime.set_timeout_async(lambda: self._startTimer(), timeout * 1e3)

    # Get current weather and traffic level
    def _getData(self):
        try:
            url = "https://export.yandex.ru/bar/reginfo.xml"
            content = urllib.request.urlopen(url).read()
            return ET.fromstring(content)
        except (IOError, ET.ParseError):
            return None

    # Get weather icon from XML element
    def _getStatus(self, el):
        day_part = el.findall('day_part')[0]

        return self._icons.get(
            day_part.find('weather_code').text,
            day_part.find('weather_type').text
        )

    # Get traffic level icon from XML element
    def _getTrafficIcon(self, el):
        return self._ticons[el.find('icon').text]

    # Update statusbar string cache
    def _updateData(self):
        xml = self._getData()

        if xml is not None:
            weather = xml.find('weather').find('day')
            title = weather.find('title').text
            status = self._getStatus(weather)
            temp = weather.findall('day_part')[0].find('temperature').text

            traffic = xml.find('traffic').find('region')
            tlevel = traffic.find('level').text
            ticon = self._getTrafficIcon(traffic)

            self._status = self._template % vars()
            return True
        else:
            self._status = None
            return False

    # Print cached status in current view
    def _showStatus(self):
        if self._status is not None:
            self._view.set_status('YandexPogoda', self._status)
