import sublime
import sublime_plugin
import urllib
import xml.etree.ElementTree as ET

POGODASTATUSBAR_SETTING_FILE = 'PogodaStatusBar.sublime-settings'

class PogodaStatusBar(sublime_plugin.EventListener):
	# https://tech.yandex.ru/weather/doc/dg/concepts/translations-docpage/
	# Иконки погоды
	_icons = {\
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

	# Иконки трафика
	_ticons = {'green': '🍏', 'yellow': '🍋', 'red': '🍅'}

	# Настройка: интервал обновлений
	_updateInterval = None
	# Настройка: шаблон вывода
	_template = None
	# Строка, которая выводится в statusbar
	_status = None
	# Была ли инициализация класса
	_activated = False
	# Текущий view (объект Sublime)
	_view = None

	def on_activated_async(self, view):
		self._run(view)

	# Запуск для указанного окна (view)
	def _run(self, view):
		self._view = view

		if not self._activated:
			settings = sublime.load_settings(POGODASTATUSBAR_SETTING_FILE)
			self._updateInterval = settings.get('update_interval', 1800)
			self._template = settings.get('template', None)

			self._updateData()
			self._startTimer()

			self._activated = True

		self._showStatus()

	# Циклический запуск таймера
	def _startTimer(self):
		self._updateData()
		self._showStatus()
		sublime.set_timeout_async(lambda: self._startTimer(), self._updateInterval * 1e3)

	# Получение погодных данных
	def _getData(self):
		try:
			url = "https://export.yandex.ru/bar/reginfo.xml"
			content = urllib.request.urlopen(url).read()
			return ET.fromstring(content)
		except (IOError, ET.ParseError):
			return None

	# Значок погоды из элемента XML
	def _getStatus(self, el):
		day_part = el.findall('day_part')[0]

		return self._icons.get(\
			day_part.find('weather_code').text,
			day_part.find('weather_type').text
		)

	# Иконка трафика из элемента XML
	def _getTrafficIcon(self, el):
		return self._ticons[el.find('icon').text]

	# Обновление кеша строки statusbar
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
		else:
			self._status = None

	# Выводим статус в текущий view
	def _showStatus(self):
		if self._status is not None:
			self._view.set_status('YandexPogoda', self._status)


