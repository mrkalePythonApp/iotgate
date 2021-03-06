# -*- coding: utf-8 -*-
"""Plugin module representing the cloud service ThingSpeak.

- The module receives data from several MQTT topics, collects it in its buffer,
  and publishes it at once into the cloud at allowed intervals.

- The plugin receives commands
  - publish status
  - reset plugin

- The plugin receives data
  - SoC temperature in centigrades from plugin `server`.
  - Activity status of the cooling fan from plugin 'sfan'. The plugin forwards
    published fan status to the cloud.

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
from time import time

# Custom library modules
import paho.mqtt.publish as mqttpublish
from gbj_sw import iot as modIot
from gbj_sw import timer as modTimer


class Device(modIot.Plugin):
    """Plugin class."""

    class Parameter(Enum):
        """Enumeration of plugin parameters for MQTT publishing topics."""
        PERIOD = 'period'
        CHANNEL_ID = 'channel'
        CLOUD_DATA = 'cloud'

    class Source(Enum):
        """Enumeration of depending plugins parameters."""
        TEMPERATURE_SYSTEM_DID = 'server'
        COOLING_FAN_DID = 'sfan'

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
        CLIENT_ID = socket.gethostname()
        FAN_STATUS_PREFIX = 'Fan-'

    class CloudBuffer(Enum):
        """Semantics of used cloud status and fields. Max. 8 fields allowed."""
        FAN_STATUS = 'status'
        TEMPERATURE_SERVER = 'field1'

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        self._cloudprm = {}
        self._buffer = {}  # Buffer for cloud fields
        self._timestamp = None  # Time of recent publishing to cloud
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_publish,
                                     name='ThingSpeak')
        # Device parameters
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
    def did(self):
        """Device identifier."""
        return modIot.get_did(__name__)

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
# Cloud actions
###############################################################################
    def _setup_cloud(self) -> NoReturn:
        """Define cloud management parameters."""
        section = self.CloudConfig.SECTION.value
        self._cloudprm[self.CloudConfig.CLIENT_ID.name] = \
            self.CloudConfig.CLIENT_ID.value + f'_{self.did}'
        self._cloudprm[self.CloudConfig.OPTION_HOST.name] = \
            self.config.option(self.CloudConfig.OPTION_HOST.value,
                               section,
                               self.CloudConfig.DEFAULT_HOST.value)
        self._cloudprm[self.CloudConfig.OPTION_PORT.name] = \
            int(self.config.option(self.CloudConfig.OPTION_PORT.value,
                                   section,
                                   self.CloudConfig.DEFAULT_PORT.value))
        self._cloudprm[self.CloudConfig.OPTION_MQTT_API_KEY.name] = \
            self.config.option(self.CloudConfig.OPTION_MQTT_API_KEY.value,
                               section)
        self._cloudprm[self.CloudConfig.OPTION_CHANNEL_ID.name] = \
            self.config.option(self.CloudConfig.OPTION_CHANNEL_ID.value,
                               section)
        self._cloudprm[self.CloudConfig.OPTION_WRITE_API_KEY.name] = \
            self.config.option(self.CloudConfig.OPTION_WRITE_API_KEY.value,
                               section)
        # Add channel id to plugin status parameter
        self.set_param(self._cloudprm[self.CloudConfig.OPTION_CHANNEL_ID.name],
                       self.Parameter.CHANNEL_ID)
        # Initialize buffer
        for field in self.CloudBuffer:
            if field.value not in self._buffer.keys():
                self._buffer[field.value] = None

    @property
    def status_fan(self) -> str:
        """Recent received fan status from MQTT broker."""
        return self._buffer[self.CloudBuffer.FAN_STATUS.value]

    @status_fan.setter
    def status_fan(self, status: modIot.Status) -> NoReturn:
        """Remap and update fan status."""
        status_new = \
            f'{self.CloudConfig.FAN_STATUS_PREFIX.value}' \
            f'{status.value}'
        self._buffer[self.CloudBuffer.FAN_STATUS.value] = status_new

    def publish_buffer(self) -> NoReturn:
        """Publish values in buffer."""
        # Check plugin started
        if self.CloudConfig.OPTION_CHANNEL_ID.name not in self._cloudprm:
            self._logger.debug('Plugin not started yet')
            return
        # Check publishing period
        if self._timestamp:
            elapsed = time() - self._timestamp
            if elapsed < self.Timer.MINIMUM.value:
                log = \
                    f'Ignored frequent publishing after {elapsed:.1f}s' \
                    f' less than minimum {self.Timer.MINIMUM.value:.1f}s'
                self._logger.warning(log)
                return
            if self._timer and elapsed < self.period:
                log = \
                    f'Timer restarted after {self._timer.elapsed:.1f}s' \
                    f' less than period {self.period:.1f}s'
                self._logger.warning(log)
                self._timer.restart()
        # Construct message payload
        items = []
        for field in self.CloudBuffer:
            field_name = field.value
            field_value = self._buffer[field_name] \
                if field_name in self._buffer else None
            if field_value:
                field_item = f'{field_name}={field_value}'
                items.append(field_item)
        payload = '&'.join(items)
        # Publish payload
        if payload:
            channel = self._cloudprm[self.CloudConfig.OPTION_CHANNEL_ID.name]
            items = [
                'channels',
                channel,
                'publish',
                self._cloudprm[self.CloudConfig.OPTION_WRITE_API_KEY.name],
            ]
            msg = f'Publishing to cloud'
            try:
                log = f'{msg}, {channel=}, message: {payload}'
                self._logger.debug(log)
                topic = self.Separator.TOPIC.value.join(items)
                mqttpublish.single(
                    topic,
                    payload=payload,
                    hostname=self._cloudprm[self.CloudConfig.OPTION_HOST.name],
                    port=self._cloudprm[self.CloudConfig.OPTION_PORT.name],
                    auth={
                        'username':
                            self._cloudprm[self.CloudConfig.CLIENT_ID.name],
                        'password':
                            self._cloudprm[
                                self.CloudConfig.OPTION_MQTT_API_KEY.name],
                    }
                )
                self._timestamp = time()
                self._buffer[self.CloudBuffer.FAN_STATUS.value] = None
            except socket.gaierror as errmsg:
                log = f'{msg} failed: {errmsg}'
                self._logger.error(log)
            else:
                # Publish payload to a MQTT broker as DATA
                message = payload
                topic = self.get_topic(
                    modIot.Category.DATA,
                    self.Parameter.CLOUD_DATA,
                    modIot.Measure.VALUE)
                log = modIot.get_log(message,
                                     modIot.Category.DATA,
                                     self.Parameter.CLOUD_DATA,
                                     modIot.Measure.VALUE)
                self._logger.debug(log)
                self.mqtt_client.publish(message, topic)
        else:
            self._logger.debug('Nothing published to cloud')

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self._setup_cloud()
        self.publish_status()
        if self._timer:
            self._timer.start()

    def finish(self):
        if self._timer:
            self._timer.stop()
        super().finish()

    def _callback_timer_publish(self):
        """Publish data from cache."""
        self.publish_buffer()

    def process_own_command(self,
                            value: str,
                            parameter: Optional[str],
                            measure: Optional[str]) -> NoReturn:
        """Process command for this device only.

        Arguments
        ---------
        value
            Payload from an MQTT message.
        parameter
            Parameter taken from an MQTT topic corresponding to some item value
            from Parameter enumeration.
        measure
            Measure taken from an MQTT topic corresponding to some item value
            from Measure enumeration.

        """
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
        """Process data from any device except this one.

        Arguments
        ---------
        value
            Payload from an MQTT message.
        parameter
            Parameter taken from an MQTT topic corresponding to some item value
            from Parameter enumeration.
        measure
            Measure taken from an MQTT topic corresponding to some item value
            from Measure enumeration.
        device
            Object of a sourcing device (plugin), which sent an MQTT message.

        """
        # Process data from plugin 'server'
        if device.did == self.Source.TEMPERATURE_SYSTEM_DID.value:
            # Process SoC temperature
            if parameter == device.Parameter.TEMPERATURE.value \
                    and measure == modIot.Measure.VALUE.value:
                try:
                    temperature = float(value)
                except (TypeError, ValueError):
                    log = f'Ignored invalid temperature {value=}'
                    self._logger.warning(log)
                else:
                    self._buffer[self.CloudBuffer.TEMPERATURE_SERVER.value] \
                        = temperature
                    log = f'Received SoC {temperature=}'
                    self._logger.debug(log)

    def process_status(self,
                       value: str,
                       parameter: Optional[str],
                       measure: Optional[str],
                       device: modIot.Plugin) -> NoReturn:
        """Process status of any device except this one.

        Arguments
        ---------
        value
            Payload from an MQTT message.
        parameter
            Parameter taken from an MQTT topic corresponding to some item value
            from Parameter enumeration.
        measure
            Measure taken from an MQTT topic corresponding to some item value
            from Measure enumeration.
        device
            Object of a sourcing device (plugin), which sent an MQTT message.

        """
        # Process status from 'fan'
        if device.did == self.Source.COOLING_FAN_DID.value:
            if parameter == device.Parameter.ACTIVITY.value \
                    and measure is None:
                status = value.strip()
                if status in [
                        modIot.Status.ACTIVE.value,
                        modIot.Status.IDLE.value,
                        modIot.Status.UNKNOWN.value,
                ]:
                    self.status_fan = modIot.Status(status)
                    log = f'Received {status=}'
                    self._logger.debug(log)
                    self.publish_buffer()
                else:
                    log = f'Ignored uknown {status=}'
                    self._logger.warning(log)
