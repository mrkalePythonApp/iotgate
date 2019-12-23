# -*- coding: utf-8 -*-
"""Plugin module for processing SoC events, mostly system temperature
 measurement.

 """
__version__ = '0.1.0'
__status__ = 'Beta'
__author__ = 'Libor Gabaj'
__copyright__ = 'Copyright 2019, ' + __author__
__credits__ = [__author__]
__license__ = 'MIT'
__maintainer__ = __author__
__email__ = 'libor.gabaj@gmail.com'


# Standard library modules
import logging
from random import randint
from enum import Enum
from typing import Optional, Any, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import timer as modTimer


class Parameter(modIot.Parameter):
    """Enumeration of expected MQTT topic parameters."""
    TEMPERATURE = 'temp'
    PERIOD = 'period'


class device(modIot.Plugin):
    """Plugin class."""

    TIMER_PERIOD_DEF = 5.0
    TIMER_PERIOD_MIN = 1.0
    TIMER_PERIOD_MAX = 60.0
    """float: Periods for temperature timer."""

    DEFAULT_TEMPERATURE_MAX = 75.0
    """float: Maximal allowed temperature in case not read from the system."""

    RANDOM_TEMPERATURE_MIN = 40.0
    """float: Minimal limit for randomly generated temperature."""

    RANDOM_TEMPERATURE_MAX = 70.0
    """float: Maximal limit for randomly generated temperature."""

    RANDOM_TEMPERATURE_RES = 10
    """int: Resolution of generated temperature."""

    def __init__(self):
        super().__init__()
        # Logging
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        self._logger.debug(
            f'Instance of "{self.__class__.__name__}" created: {self.id}')
        # Device attributes
        self._temperature_max = None
        self._temperature = None
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_temperature,
                                     name='SoCtemp')
        # Device parameters
        self.set_param(self.temperature_maximal,
                       Parameter.TEMPERATURE,
                       modIot.Measure.MAXIMUM)

    @property
    def id(self):
        return 'server'

    @property
    def period(self) -> float:
        """Current timer period in seconds."""
        if not hasattr(self, '_period') or self._period is None:
            self._period = self.TIMER_PERIOD_DEF
        return self._period

    @period.setter
    def period(self, period: float):
        """Sanitize and set new timer period in seconds."""
        try:
            self._period = abs(float(period))
        except (ValueError, TypeError):
            pass
        else:
            self._period = min(max(self._period, self.TIMER_PERIOD_MIN),
                               self.TIMER_PERIOD_MAX)
        finally:
            self.period

###############################################################################
# MQTT actions
###############################################################################
    def publish_status(self):
        message = f'{self._temperature_max:.1f}'
        topic = self.get_topic(
                modIot.Category.STATUS,
                Parameter.TEMPERATURE,
                modIot.Measure.MAXIMUM)
        try:
            self.mqtt_client.publish(message, topic)
            msg = f'Published to MQTT {topic=}: {message}'
            self._logger.debug(msg)
        except Exception as errmsg:
            self._logger.error(errmsg)

    def publish_temperature(self):
        message = f'{self.temperature:.1f}'
        topic = self.get_topic(
                modIot.Category.DATA,
                Parameter.TEMPERATURE,
                modIot.Measure.VALUE)
        try:
            self.mqtt_client.publish(message, topic)
            msg = f'Published to MQTT {topic=}: {message}'
            self._logger.debug(msg)
        except Exception as errmsg:
            self._logger.error(errmsg)

    def publish_percentage(self):
        percentage = self.temp2perc(self._temperature)
        message = f'{percentage:.1f}'
        topic = self.get_topic(
                modIot.Category.DATA,
                Parameter.TEMPERATURE,
                modIot.Measure.PERCENTAGE)
        try:
            self.mqtt_client.publish(message, topic)
            msg = f'Published to MQTT {topic=}: {message}'
            self._logger.debug(msg)
        except Exception as errmsg:
            self._logger.error(errmsg)

###############################################################################
# Temperature actions
###############################################################################
    def _read_temperature(self, system_path: str) -> float:
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

    @property
    def temperature_maximal(self) -> float:
        """Cached system maximal temperature."""
        if self._temperature_max is None:
            temperature = None
            try:
                temperature = self._read_temperature(
                    '/sys/class/thermal/thermal_zone0/trip_point_0_temp'
                )
            except FileNotFoundError:
                temperature = self.DEFAULT_TEMPERATURE_MAX
            except Exception as errmsg:
                self._logger.error(errmsg)
            finally:
                if temperature is not None:
                    self._temperature_max = temperature
        return self._temperature_max

    @property
    def temperature(self) -> float:
        """Read system current temperature."""
        self._temperature = None
        try:
            self._temperature = self._read_temperature(
                '/sys/class/thermal/thermal_zone0/temp'
            )
        except FileNotFoundError:
            temperature = randint(
                self.RANDOM_TEMPERATURE_MIN * self.RANDOM_TEMPERATURE_RES,
                self.RANDOM_TEMPERATURE_MAX * self.RANDOM_TEMPERATURE_RES)
            self._temperature = float(
                temperature / self.RANDOM_TEMPERATURE_RES)
        except Exception as errmsg:
            self._logger.error(errmsg)
        return self._temperature

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
        percentage = None
        self.temperature_maximal
        if self._temperature_max:
            percentage = temperature / self._temperature_max * 100.0
        return percentage

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
        temperature = None
        self.temperature_maximal
        if self._temperature_max:
            temperature = percentage / 100.0 * self._temperature_max
        return temperature

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

    def _callback_timer_temperature(self, *arg, **kwargs):
        """Publish temperature."""
        self.publish_temperature()
        self.publish_percentage()

    def process_command(self,
                        value: str,
                        parameter: str,
                        measure: Optional[str]) -> NoReturn:
        """Process command intended just for this device."""
        # Detect timer period change
        if parameter == Parameter.PERIOD.value \
                and (measure is None or measure == modIot.Measure.VALUE.value):
            msg = f'Timer period'
            old = self.period
            self.period = value
            if old == self.period:
                self._logger.debug(f'{msg} "{value}" ignored')
            else:
                self._timer.period = self.period
                self._logger.debug(f'{msg} changed to {self.period}s')

    def process_status(self,
                       value: str,
                       parameter: str,
                       measure: Optional[str],
                       device: object) -> NoReturn:
        """Process status of any device even this one."""
        pass

    def process_data(self,
                     value: str,
                     parameter: str,
                     measure: Optional[str],
                     device: object) -> NoReturn:
        """Process data from any device even this one."""
        pass
