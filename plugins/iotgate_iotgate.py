# -*- coding: utf-8 -*-
"""Plugin module representing IoT gate application.

- The module registers all other plugins as devices representing real hardware
  items, actuators, and sensors.

- The module mediates communication with MQTT broker and distributes MQTT
  messages to all registered devices for processing.

- The plugin receives commands for
  - publishing status
  - changing MQTT reconnect timer period within hardcoded range

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
from enum import Enum
from typing import Optional, Any, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import mqtt as modMqtt
from gbj_sw import timer as modTimer


class Device(modIot.Plugin):
    """Plugin class."""

    class Parameter(Enum):
        """Enumeration of plugin parameters for MQTT publishing topics."""
        PERIOD = 'period'

    class Timer(Enum):
        """Period parameters for MQTT reconnecting timer."""
        DEFAULT = 30.0
        MINIMUM = 5.0
        MAXIMUM = 180.0

    class MqttConfig(Enum):
        """MQTT configuration parameters for INI file."""
        SECTION = 'MQTTbroker'  # INI section
        OPTION_HOST = 'host'
        OPTION_PORT = 'port'
        OPTION_USERNAME = 'username'
        OPTION_PASSWORD = 'password'
        DEFAULT_HOST = 'localhost'
        DEFAULT_PORT = 1883

    def __init__(self) -> NoReturn:
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        # Device attributes
        self.devices = {}  # List of processed proxy devices
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_reconnect,
                                     name='MqttRecon')
        # Device parameters
        self.set_param(self.period,
                       self.Parameter.PERIOD,
                       modIot.Measure.VALUE)
        self.set_param(self.period,
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
# MQTT actions
###############################################################################
    def _setup_mqtt(self) -> NoReturn:
        """Define MQTT management."""
        self.mqtt_client = modMqtt.MqttBroker(
            clientid=self.did,
            message=self._callback_on_message,
        )
        # Set last will and testament
        topic = self.get_topic(modIot.Category.STATUS)
        self.mqtt_client.lwt(modIot.Status.OFFLINE.value, topic)
        # Connect to MQTT broker
        section = self.MqttConfig.SECTION.value
        username = self.config.option(self.MqttConfig.OPTION_USERNAME.value,
                                      section)
        password = self.config.option(self.MqttConfig.OPTION_PASSWORD.value,
                                      section)
        host = self.config.option(self.MqttConfig.OPTION_HOST.value,
                                  section,
                                  self.MqttConfig.DEFAULT_HOST.value)
        port = self.config.option(self.MqttConfig.OPTION_PORT.value,
                                  section,
                                  self.MqttConfig.DEFAULT_PORT.value)
        self.mqtt_client.connect(
            username=username,
            password=password,
            host=host,
            port=port,
            )

    def _callback_on_message(
            self,
            userdata: Any,
            message: modMqtt.mqttclient.MQTTMessage) -> NoReturn:
        """Process actions when a non-filtered message has been received.

        Arguments
        ---------
        userdata
            The private user data.
        message
            The object with members `topic`, `payload`, `qos`, `retain`.

        """
        topic = message.topic
        payload = message.payload
        if not payload:
            log = f'Ignored empty MQTT message'
            self._logger.warning(log)
            return
        payload = payload.decode('utf-8')
        # Parse topic
        maxvars = 4
        msg_parts = topic.split(self.Separator.TOPIC.value, maxvars)
        if len(msg_parts) > maxvars:
            log = f'Ignored too long topic "{topic}"'
            self._logger.warning(log)
            return
        msg_parts.extend([None] * (maxvars - len(msg_parts)))
        device_id, category, parameter, measure = msg_parts
        # Process device's own command
        if category == modIot.Category.COMMAND.value:
            if device_id in self.devices:
                device = self.devices[device_id]
                if device.process_own_command:
                    device.userdata = userdata
                    device.process_own_command(payload, parameter, measure)
        # Process foreign status, data, and command (interdevice dependency)
        else:
            for plugin in self.devices.values():
                if device_id == plugin.did:
                    continue
                device = self.devices[device_id]  # Source device
                plugin.userdata = userdata
                try:
                    if category == modIot.Category.STATUS.value:
                        plugin.process_status(payload, parameter, measure,
                                              device)
                    elif category == modIot.Category.DATA.value:
                        plugin.process_data(payload, parameter, measure,
                                            device)
                    elif category == modIot.Category.COMMAND.value:
                        plugin.process_command(payload, parameter, measure,
                                               device)
                except AttributeError:
                    continue

    def publish_connect(self, status: modIot.Status):
        """Publish connection status to MQTT broker."""
        message = status.value
        topic = self.get_topic(modIot.Category.STATUS)
        log = modIot.get_log(message, modIot.Category.STATUS)
        self._logger.debug(log)
        self.mqtt_client.publish(message, topic)

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self._setup_mqtt()
        self.publish_connect(modIot.Status.ONLINE)
        self.publish_status()
        # Start all devices except this one and subscribe to their MQTT topics
        for device in self.devices.values():
            if device != self:
                device.config = self.config
                device.mqtt_client = self.mqtt_client
                device.begin()
            self.mqtt_client.subscribe(device.device_topic)
        self._timer.start()

    def finish(self):
        self._timer.stop()
        # Stop all devices plugins
        for device in self.devices.values():
            if device == self:
                continue
            device.finish()
        self.publish_connect(modIot.Status.OFFLINE)
        self.mqtt_client.disconnect()
        super().finish()

    def _callback_timer_reconnect(self):
        """Execute MQTT reconnect."""
        if not self.mqtt_client.connected:
            self.mqtt_client.reconnect()

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
        # Change timer period
        if parameter == self.Parameter.PERIOD.value \
                and measure == modIot.Measure.VALUE.value:
            self.period = value
            log = f'Timer period set to {self.period}s'
            self._logger.warning(log)
