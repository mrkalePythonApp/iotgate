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
__copyright__ = 'Copyright 2019, ' + __author__
__credits__ = [__author__]
__license__ = 'MIT'
__maintainer__ = __author__
__email__ = 'libor.gabaj@gmail.com'


# Standard library modules
import logging
from os import path
from enum import Enum
from typing import Optional, Any, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import mqtt as modMqtt
from gbj_sw import timer as modTimer


class Parameter(modIot.Parameter):
    """Enumeration of expected MQTT topic parameters."""
    PERIOD = 'period'


class device(modIot.Plugin):
    """Plugin class."""

    class Timer(Enum):
        """Period parameters for MQTT reconnecting timer."""
        DEFAULT = 30.0
        MINIMUM = 5.0
        MAXIMUM = 180.0


    class MqttConfig(Enum):
        """MQTT configuration parameters for INI file."""
        GROUP_BROKER = 'MQTTbroker'  # INI section

    def __init__(self) -> NoReturn:
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        # Device attributes
        self.config = None  # Access to configuration INI file
        self.devices = {}  # List of processed proxy devices
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_reconnect,
                                     name='MqttRecon')
        # Device parameters
        self.set_param(self.period,
                       Parameter.PERIOD,
                       modIot.Measure.DEFAULT)
        self.set_param(self.Timer.MINIMUM.value,
                       Parameter.PERIOD,
                       modIot.Measure.MINIMUM)
        self.set_param(self.Timer.MAXIMUM.value,
                       Parameter.PERIOD,
                       modIot.Measure.MAXIMUM)

    @property
    def id(self) -> str:
        name = path.splitext(__name__)[0]
        id = name.split('_')[1]
        return id

    @property
    def period(self) -> float:
        """Current timer period in seconds."""
        if not hasattr(self, '_period') or self._period is None:
            self._period = self.Timer.DEFAULT.value
        return self._period

    @period.setter
    def period(self, period: float) -> NoReturn:
        """Sanitize and set new timer period in seconds."""
        try:
            old = self.period
            self._period = float(period or self.Timer.DEFAULT.value)
            if old == self._period:
                raise ValueError
        except (ValueError, TypeError):
            pass
        else:
            # Sanitize new period
            self._period = min(max(abs(self._period),
                                   self.Timer.MINIMUM.value),
                               self.Timer.MAXIMUM.value)
            # Register new period
            self.set_param(self._period,
                           Parameter.PERIOD,
                           modIot.Measure.DEFAULT)
            # Publish new period
            self.publish_param(Parameter.PERIOD, modIot.Measure.DEFAULT)
            # Apply new period
            if self._timer:
                self._timer.period = self._period

###############################################################################
# MQTT actions
###############################################################################
    def _setup_mqtt(self) -> NoReturn:
        """Define MQTT management."""
        self.mqtt_client = modMqtt.MqttBroker(
            clientid=self.id,
            connect=self._callback_on_connect,
            disconnect=self._callback_on_disconnect,
            subscribe=self._callback_on_subscribe,
            message=self._callback_on_message,
        )
        # Set last will and testament
        try:
            topic = self.get_topic(modIot.Category.STATUS)
            self.mqtt_client.lwt(modIot.Status.OFFLINE.value, topic)
        except Exception as errmsg:
            self._logger.error(errmsg)
        # Connect to MQTT broker
        try:
            section = self.MqttConfig.GROUP_BROKER.value
            username = self.config.option('username', section)
            password = self.config.option('password', section)
            host = self.config.option('host', section)
            port = self.config.option('port', section)

            self.mqtt_client.connect(
                username=username,
                password=password,
                host=host,
                port=port,
                )
        except Exception as errmsg:
            self._logger.error(errmsg)

    def _callback_on_connect(self,
                             client: modMqtt.mqttclient,
                             userdata: Any,
                             flags: dict(),
                             rc: int) -> NoReturn:
        """Process actions when the broker responds to a connection request.

        Arguments
        ---------
        client
            MQTT client instance for this callback.
        userdata
            The private user data.
        flags
            Response flags sent by the MQTT broker.
        rc
            The connection result (result code).

        """
        if rc == 0:
            msg = f'Connected to {self.mqtt_client}: {userdata} ({rc=})'
            self._logger.debug(msg)
        else:
            errmsg = f'Connection to MQTT broker failed: {userdata} ({rc=})'
            self._logger.error(errmsg)

    def _callback_on_disconnect(self,
                                client: modMqtt.mqttclient,
                                userdata: Any,
                                rc: int) -> NoReturn:
        """Process actions when the client disconnects from the broker.

        Arguments
        ---------
        client
            MQTT client instance for this callback.
        userdata
            The private user data.
        rc
            The connection result (result code).

        See Also
        --------
        gbj_sw.mqtt._on_connect()
            Description of callback arguments for proper utilizing.

        """
        msg = f'Disconnected from {self.mqtt_client}: {userdata} ({rc=})'
        self._logger.warning(msg)

    def _mqtt_message_log(
            self,
            message: modMqtt.mqttclient.MQTTMessage) -> NoReturn:
        """Log receiving from an MQTT topic.

        Arguments
        ---------
        message
            This is an object with members `topic`, `payload`, `qos`, `retain`.

        """
        if message.payload is None:
            payload = "None"
        elif len(message.payload):
            payload = message.payload.decode('utf-8')
        else:
            payload = "Empty"
        topic = message.topic
        qos = message.qos
        retain = bool(message.retain)
        msg = f'MQTT {topic=}, {qos=}, {retain=}: {payload}'
        self._logger.debug(msg)

    def _callback_on_subscribe(self,
                               client: modMqtt.mqttclient,
                               userdata: Any,
                               mid: int,
                               granted_qos: int) -> NoReturn:
        """Process actions when the broker responds to a subscribe request.

        Arguments
        ---------
        client
            MQTT client instance for this callback.
        userdata
            The private user data.
        mid
            The message ID from the subscribe request.
        granted_qos
            The list of integers that give the QoS level the broker has granted
            for each of the different subscription requests.

        """
        pass

    def _callback_on_message(
        self,
        client: modMqtt.mqttclient,
        userdata: Any,
        message: modMqtt.mqttclient.MQTTMessage) -> NoReturn:
        """Process actions when a non-filtered message has been received.

        Arguments
        ---------
        client
            MQTT client instance for this callback.
        userdata
            The private user data.
        message
            The object with members `topic`, `payload`, `qos`, `retain`.

        Notes
        -----
        - The topic that the client subscribes to and the message does not match
        an existing topic filter callback.
        - Use message_callback_add() to define a callback that will be called for
        specific topic filters. This function serves as fallback when none
        topic filter matched.

        """
        self._mqtt_message_log(message)
        topic = message.topic
        payload = message.payload
        if payload is None or len(payload) == 0:
            self._logger.warning(f'Ignored empty MQTT message')
            return
        payload = payload.decode('utf-8')
        # Parse topic
        maxvars = 4
        msg_parts = topic.split(self.Separator.TOPIC.value, maxvars)
        if len(msg_parts) > maxvars:
            self._logger.warning('Ignored too long topic "{topic}"')
            return
        msg_parts.extend([None] * (maxvars - len(msg_parts)))
        device_id, category, parameter, measure = msg_parts
        # Process device's own command
        if category == modIot.Category.COMMAND.value:
            if device_id in self.devices:
                device = self.devices[device_id]
                device.process_command(payload, parameter, measure)
        # Process foreign status and data (interdevice dependency)
        else:
            for device in self.devices.values():
                if device_id == device.id:
                    continue
                if category == modIot.Category.STATUS.value:
                    device.process_status(payload, parameter, measure, device)
                elif category == modIot.Category.DATA.value:
                    device.process_data(payload, parameter, measure, device)

    def publish_connect(self, status: modIot.Status):
        """Publish connection status to MQTT broker."""
        message = status.value
        topic = self.get_topic(modIot.Category.STATUS)
        log = self.get_log(message, modIot.Category.STATUS)
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

    def _callback_timer_reconnect(self, *arg, **kwargs):
        """Execute MQTT reconnect."""
        if self.mqtt_client.connected:
            return
        self._logger.warning('Reconnecting to MQTT broker')
        try:
            self.mqtt_client.reconnect()
        except SystemError as errmsg:
            errmsg = f'Reconnection to MQTT broker failed with error: {errmsg}'
            self._logger.error(errmsg)

    def process_command(self,
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
                self.period = self.Timer.DEFAULT.value
                self.publish_status()
                self._logger.warning(f'Device reset')
        # Change timer period
        if parameter == Parameter.PERIOD.value \
                and measure == modIot.Measure.VALUE.value:
            self.period = value
            self._logger.warning(f'Timer period set to {self.period}s')
