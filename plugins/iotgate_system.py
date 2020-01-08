# -*- coding: utf-8 -*-
"""Plugin module representing the operating system of the IoT server.

- The module mediates SoC temperature sensor and measures the temeperature
  directly by reading corresponding system file(s).

- The plugin receives commands for
  - publishing status
  - changing measurement timer period within hardcoded range

 """
__version__ = '0.1.0'
__status__ = 'Beta'
__author__ = 'Libor Gabaj'
__copyright__ = 'Copyright 2019-2020, ' + __author__
__credits__ = [__author__]
__license__ = 'MIT'
__maintainer__ = __author__
__email__ = 'libor.gabaj@gmail.com'


# Standard library modules
import logging
from random import randint
from enum import Enum
from typing import Optional, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import timer as modTimer
from gbj_sw import statfilter as modFilter


def read_temperature(system_path: str) -> float:
    """Read system file and interpret the content as the temperature.

    Arguments
    ---------
    system_path
        Full path to a file with system temperature.

    Returns
    -------
    temperature
        System temperature in centigrades Celsius.
        If some problem occurs with reading system file, the None is
        provided.

    Raises
    -------
    ValueError
        Content of the system file cannot be converted to float.

    """
    with open(system_path) as system_file:
        content = system_file.read()
        temperature = float(content)
        # Raspbian with temp in centigrades, other Pis in millicentigrades
        if temperature > 85.0:
            temperature /= 1000.0
    return temperature


class Device(modIot.Plugin):
    """Plugin class."""

    class Parameter(Enum):
        """Enumeration of plugin parameters for MQTT publishing topics."""
        PERIOD = 'period'
        TEMPERATURE = 'temp'

    class Timer(Enum):
        """Period parameters for temperature reading timer."""
        DEFAULT = 5.0
        MINIMUM = 1.0
        MAXIMUM = 60.0

    class RandomTemperature(Enum):
        """Parameters for randomly generated temperature on Windows."""
        RESOLUTION = 10  # int: Resolution of generated temperature
        DEFAULT = 75.0   # Maximal allowed temperature
        MINIMUM = 40.0   # Interval for random temperatures
        MAXIMUM = 70.0

    def __init__(self) -> NoReturn:
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        # Device attributes
        self._temperature_max = None
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_temperature,
                                     name='SoCtemp')
        # self._filter = modFilter.Running()
        # self._filter.stat_type = self._filter.StatisticType.AVERAGE
        # self._filter.stat_type = self._filter.StatisticType.MEDIAN
        self._filter = modFilter.Exponential()
        self._filter.factor = self._filter.Factor.OPTIMAL.value
        # Device parameters
        self.set_param(self.temperature_maximal,
                       self.Parameter.TEMPERATURE,
                       modIot.Measure.MAXIMUM)
        self.set_param(self.period,
                       self.Parameter.PERIOD,
                       modIot.Measure.VALUE)
        self.set_param(self.Timer.DEFAULT.value,
                       self.Parameter.PERIOD,
                       modIot.Measure.DEFAULT)
        self.set_param(self.Timer.MINIMUM.value,
                       self.Parameter.PERIOD,
                       modIot.Measure.MINIMUM)
        self.set_param(self.Timer.MAXIMUM.value,
                       self.Parameter.PERIOD,
                       modIot.Measure.MAXIMUM)

    @property
    def did(self) -> str:
        """Device identifier."""
        return 'server'

    @property
    def period(self) -> float:
        """Current timer period in seconds."""
        val = self.get_param(self.Parameter.PERIOD,
                             modIot.Measure.VALUE,
                             self.Timer.DEFAULT.value)
        return val

    @period.setter
    def period(self, period: float):
        """Sanitize and set new timer period in seconds."""
        try:
            old = self.period
            new = float(period or self.Timer.DEFAULT.value)
            if old == new:
                raise ValueError
        except (ValueError, TypeError):
            pass
        else:
            # Sanitize new value
            new = min(max(abs(new), self.Timer.MINIMUM.value),
                      self.Timer.MAXIMUM.value)
            # Register new value
            self.set_param(new, self.Parameter.PERIOD, modIot.Measure.VALUE)
            # Publish new value
            self.publish_param(self.Parameter.PERIOD, modIot.Measure.VALUE)
            # Apply new value
            if self._timer:
                self._timer.period = new

###############################################################################
# MQTT actions
###############################################################################
    def publish_temperature(self):
        """Read and publish current temperature."""
        message = f'{self.temperature:.1f}'
        topic = self.get_topic(
            modIot.Category.DATA,
            self.Parameter.TEMPERATURE,
            modIot.Measure.VALUE)
        log = self.get_log(message,
                           modIot.Category.DATA,
                           self.Parameter.TEMPERATURE,
                           modIot.Measure.VALUE)
        self._logger.debug(log)
        self.mqtt_client.publish(message, topic)

    def publish_percentage(self):
        """Calculate and publish percentage of recent current temperature."""
        percentage = self.temp2perc(self._filter.result())
        message = f'{percentage:.1f}'
        topic = self.get_topic(
            modIot.Category.DATA,
            self.Parameter.TEMPERATURE,
            modIot.Measure.PERCENTAGE)
        log = self.get_log(message,
                           modIot.Category.DATA,
                           self.Parameter.TEMPERATURE,
                           modIot.Measure.PERCENTAGE)
        self._logger.debug(log)
        self.mqtt_client.publish(message, topic)

###############################################################################
# Temperature actions
###############################################################################
    @property
    def temperature_maximal(self) -> float:
        """Cached system maximal temperature."""
        if self._temperature_max is None:
            try:
                self._temperature_max = read_temperature(
                    '/sys/class/thermal/thermal_zone0/trip_point_0_temp'
                )
            except FileNotFoundError:
                self._temperature_max = self.RandomTemperature.DEFAULT.value
        return self._temperature_max

    @property
    def temperature(self) -> float:
        """Read system current temperature."""
        temperature = None
        try:
            temperature = read_temperature(
                '/sys/class/thermal/thermal_zone0/temp'
            )
        except FileNotFoundError:
            resval = self.RandomTemperature.RESOLUTION.value
            minval = self.RandomTemperature.MINIMUM.value * resval
            maxval = self.RandomTemperature.MAXIMUM.value * resval
            temperature = randint(minval, maxval)
            temperature = float(temperature // resval)
        return self._filter.result(temperature)

    def temp2perc(self, temperature: float) -> float:
        """Calculate percentage from temperature.

        Arguments
        ---------
        temperature
            Value in centigrades to be converted to percentage of maximal
            value if it is saved.

        Returns
        -------
        percentage
            Input value expressed in percentage of saved maximal value
            or nothing.

        """
        try:
            return temperature / self.temperature_maximal * 100.0
        except TypeError:
            return None

    def perc2temp(self, percentage: float) -> float:
        """Calculate temperature value in centigrades from percentage.

        Arguments
        ---------
        percentage
            Value in percentage of maximal value to be converted
            to centigrades.

        Returns
        -------
        temperature
            Input value expressed in centigrades if maximal value is saved
            or nothing.

        """
        try:
            return percentage / 100.0 * self.temperature_maximal
        except TypeError:
            return None

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self.publish_status()
        self._timer.start()

    def finish(self):
        self._timer.stop()
        super().finish()

    def _callback_timer_temperature(self):
        """Publish temperature."""
        self.publish_temperature()
        self.publish_percentage()

    def process_own_command(self,
                            value: str,
                            parameter: Optional[str],
                            measure: Optional[str]) -> NoReturn:
        """Process command intended just for this device."""
        # Generic commands
        if parameter is None and measure is None:
            # Publish status
            if value == modIot.Command.GET_STATUS.value:
                self.publish_status()
            # Reset status
            if value == modIot.Command.RESET.value:
                self.period = None
                log = f'Device reset'
                self._logger.warning(log)
        # Change timer period
        if parameter == self.Parameter.PERIOD.value \
            and measure == modIot.Measure.VALUE.value:
            self.period = value
            log = f'Timer period set to {self.period}s'
            self._logger.warning(log)
