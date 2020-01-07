# -*- coding: utf-8 -*-
"""Plugin module representing the cloud service ThingSpeak.

- The module receives data from several MQTT topic, collect it in its cache,
  and publish it at once into the cloud at allowed intervals.

- The plugin receives commands
  - publish status
  - reset plugin

- The plugin receives data
  - SoC temperature in centigrades from plugin `server`


 """
__version__ = '0.1.0'
__status__ = 'Beta'
__author__ = 'Libor Gabaj'
__copyright__ = 'Copyright 2020, ' + __author__
__credits__ = [__author__]
__license__ = 'MIT'
__maintainer__ = __author__
__email__ = 'libor.gabaj@gmail.com'

# Standard library modules
import logging
import socket
from enum import Enum
from typing import Optional, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import timer as modTimer
import paho.mqtt.publish as mqttpublish


class Parameter(modIot.Parameter, Enum):
    """Enumeration of plugin parameters."""
    PERIOD = 'period'
    TEMPERATURE_DEVICE = 'server'
    TEMPERATURE_PARAM = 'temp'


class Device(modIot.Plugin):
    """Plugin class."""

    class Timer(Enum):
        """Period parameters for publishing to cloud."""
        DEFAULT = 30.0
        MINIMUM = 15.0
        MAXIMUM = 600.0

    class CloudConfig(Enum):
        """Configuration parameters for INI file."""
        SECTION = 'ThingSpeak'
        OPTION_HOST = 'host'
        OPTION_PORT = 'port'
        OPTION_MQTT_API_KEY = 'mqtt_api_key'
        OPTION_CHANNEL_ID = 'channel_id'
        OPTION_WRITE_API_KEY = 'write_api_key'
        DEFAULT_HOST = 'mqtt.thingspeak.com'
        DEFAULT_PORT = 1883

    class Fields(Enum):
        """Semantics of used cloud fields. Max. 8 allowed."""
        TEMPERATURE_SERVER = 'field1'

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        # Cloud attributes
        section = self.CloudConfig.SECTION.value
        self._clientid = f'{socket.gethostname()}_{self.did}'
        self._host = self.config.option(self.CloudConfig.OPTION_HOST, section,
                                        self.CloudConfig.DEFAULT_HOST)
        self._port = self.config.option(self.CloudConfig.OPTION_PORT, section,
                                        self.CloudConfig.DEFAULT_PORT)
        self._mqtt_api_key = self.config.option(
            self.CloudConfig.OPTION_MQTT_API_KEY, section)
        self._channel_id = self.config.option(
            self.CloudConfig.OPTION_CHANNEL_ID, section)
        self._write_api_key = self.config.option(
            self.CloudConfig.OPTION_WRITE_API_KEY, section)
        # Data
        self._fields = {}
        self._status = None
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_publish,
                                     name='ThingSpeak')
        # Device parameters
        self.set_param(self.period,
                       Parameter.PERIOD,
                       modIot.Measure.VALUE)
        self.set_param(self.Timer.DEFAULT.value,
                       Parameter.PERIOD,
                       modIot.Measure.DEFAULT)
        self.set_param(self.Timer.MINIMUM.value,
                       Parameter.PERIOD,
                       modIot.Measure.MINIMUM)
        self.set_param(self.Timer.MAXIMUM.value,
                       Parameter.PERIOD,
                       modIot.Measure.MAXIMUM)

    @property
    def did(self):
        """Device identifier."""
        return 'thingspeak'

    @property
    def period(self) -> float:
        """Current timer period in seconds."""
        val = self.get_param(Parameter.PERIOD,
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
            self.set_param(new, Parameter.PERIOD, modIot.Measure.VALUE)
            # Publish new value
            self.publish_param(Parameter.PERIOD, modIot.Measure.VALUE)
            # Apply new value
            if self._timer:
                self._timer.period = new

###############################################################################
# MQTT actions
###############################################################################
    def publish_fields(self):
        """Publish values in cache."""
        # for field in self.Fields:
        #     message = f'{self._fields[field.value]}'

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self.publish_status()

    def finish(self):
        self._timer.stop()
        super().finish()

    def _callback_timer_publish(self):
        """Publish data from cache."""
        self.publish_fields()

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

    def process_data(self,
                     value: str,
                     parameter: Optional[str],
                     measure: Optional[str],
                     device: modIot.Plugin) -> NoReturn:
        """Process data originating in other device."""
        # Receive data from server
        if device.did == Parameter.TEMPERATURE_DEVICE.value:
            # Process SoC temperature
            if parameter == Parameter.TEMPERATURE_PARAM.value \
                    and measure == modIot.Measure.VALUE.value:
                try:
                    temperature = float(value)
                except (TypeError, ValueError):
                    log = f'Ignored invalid temperature {value=}'
                    self._logger.warning(log)
                else:
                    self._fields[self.Fields.TEMPERATURE_SERVER.value] \
                        = temperature
                    log = f'Received SoC {temperature=}°C'
                    self._logger.debug(log)
