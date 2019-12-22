# -*- coding: utf-8 -*-
"""Plugin module for processing events and business logic of the IoT gate."""
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

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import mqtt as modMqtt
from gbj_sw import timer as modTimer


class device(modIot.Plugin):
    """Plugin class."""

    # Predefined configuration file sections related to MQTT
    GROUP_BROKER = 'MQTTbroker'
    """str: Predefined configuration section with MQTT broker parameters."""

    TIMER_PERIOD_DEF = 30.0
    TIMER_PERIOD_MIN = 5.0
    TIMER_PERIOD_MAX = 180.0
    """float: Periods for reconnect timer."""

    def __init__(self):
        super().__init__()
        # Logging
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        self._logger.debug(
            f'Instance of "{self.__class__.__name__}" created: {self.id}')
        # Device attributes
        self.config = None  # Access to configuration INI file
        self.devices = {}  # List of processed proxy devices
        self._timer = modTimer.Timer(self.period,
                                     self._callback_timer_reconnect,
                                     name='MqttRecon')
        # Device parameters

    @property
    def id(self):
        name = path.splitext(__name__)[0]
        id = name.split('_')[1]
        return id

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
    def _setup_mqtt(self):
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
            self.mqtt_client.lwt(modIot.Status.OFFLINE, topic)
        except Exception as errmsg:
            self._logger.error(errmsg)
        # Connect to MQTT broker
        try:
            username = self.config.option('username', self.GROUP_BROKER)
            password = self.config.option('password', self.GROUP_BROKER)
            host = self.config.option('host', self.GROUP_BROKER)
            port = self.config.option('port', self.GROUP_BROKER)

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
                             userdata: any,
                             flags: dict(),
                             rc: int):
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
                                userdata: any,
                                rc: int):
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
            message: modMqtt.mqttclient.MQTTMessage):
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
                               userdata: any,
                               mid: int,
                               granted_qos: int):
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

    def _callback_on_message(self,
                             client: modMqtt.mqttclient,
                             userdata: any,
                             message: modMqtt.mqttclient.MQTTMessage):
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
        if payload is not None and len(message.payload):
            payload = payload.decode('utf-8')
        # Parse topic
        msg_parts = topic.split(self.TOPIC_SEP, 4)
        if len(msg_parts) > 4:
            self._logger.warning('Ignored too long topic "{topic}"')
            return
        device_id, category, parameter, measure = None, None, None, None
        try:
            device_id, category, parameter, measure = msg_parts[0], \
                msg_parts[1], msg_parts[2], msg_parts[3]
        except IndexError:
            pass
        # Determine device and process command for it
        if device_id in self.devices:
            device = self.devices[device_id]
            if category == modIot.Category.COMMAND.value:
                device.process_command(payload, parameter, measure)
        # Process status and data for all devices except the source one
        for device in self.devices.items():
            if device_id == device.id:
                continue
            if category == modIot.Category.STATUS.value:
                device.process_status(payload,
                                      device_id,
                                      parameter,
                                      measure)
            if category == modIot.Category.DATA.value:
                device.process_data(payload,
                                    device_id,
                                    parameter,
                                    measure)

    def publish_status(self, status: modIot = modIot.Status.ONLINE):
        message = status
        topic = self.get_topic(modIot.Category.STATUS)
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
        self._setup_mqtt()
        self.publish_status(modIot.Status.ONLINE)
        # Start all devices and subscribe to their MQTT topics
        for _, device in self.devices.items():
            device.mqtt_client = self.mqtt_client
            device.begin()
            self.mqtt_client.subscribe(device.device_topic)
        self._timer.start()

    def finish(self):
        self._timer.stop()
        # Stop all devices plugins
        for _, device in self.devices.items():
            device.finish()
        self.publish_status(modIot.Status.OFFLINE)
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
                        payload: str,
                        parameter: str,
                        measure: str):
        """Process command for this device."""
        pass

    def process_status(self,
                       device_id: str,
                       payload: str,
                       parameter: str,
                       measure: str):
        """Process status of any device except this one."""
        pass

    def process_data(self,
                     device_id: str,
                     payload: str,
                     parameter: str,
                     measure: str):
        """Process data from any device except this one."""
        pass
