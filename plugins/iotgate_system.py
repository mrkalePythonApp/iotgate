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
import os
from random import randint
from enum import Enum

# Custom library modules
from gbj_sw import utils as modUtils
from gbj_sw import iot as modIot


class Parameter(modIot.Parameter):
    """Enumeration of expected MQTT topic parameters."""
    TEMPERATURE = 'temp'


class device(modIot.Plugin):
    """Plugin class."""

    def __init__(self):
        super().__init__()
        # Logging
        self._logger.debug('Instance of %s created: %s',
                           self.__class__.__name__, self.id)
        # Device attributes
        self._temperature_max = None
        # Device parameters
        self.set_param(self.temperature_maximal,
                       Parameter.TEMPERATURE,
                       modIot.Measure.MAXIMUM)

    @property
    def id(self):
        name = os.path.splitext(__name__)[0]
        id = name.split('_')[1]
        return id

###############################################################################
# MQTT actions
###############################################################################
    def publish_status(self):
        message = f'{self._temperature_max}'
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

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self.publish_status()

    def finish(self):
        super().finish()

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
                temperature = 75.0
            except Exception as errmsg:
                self._logger.error(errmsg)
            finally:
                if temperature is not None:
                    self._temperature_max = temperature
        return self._temperature_max

    @property
    def temperature(self) -> float:
        """Read system current temperature."""
        temperature = None
        try:
            temperature = self._read_temperature(
                '/sys/class/thermal/thermal_zone0/temp'
            )
        except FileNotFoundError:
            temperature = float(randint(40, 70))
        except Exception as errmsg:
            self._logger.error(errmsg)
        return temperature

    @property
    def percentage(self) -> float:
        """Read system current temperature and express it in percentage."""
        return self.temp2perc(self.temperature)

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
