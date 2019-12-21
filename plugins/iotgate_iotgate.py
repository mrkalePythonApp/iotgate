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
import os

# Custom library modules
from gbj_sw import iot as modIot
from gbj_sw import mqtt as modMqtt


class device(modIot.Plugin):
    """Plugin class."""

    # Predefined configuration file sections related to MQTT
    GROUP_BROKER = 'MQTTbroker'
    """str: Predefined configuration section with MQTT broker parameters."""

    def __init__(self):
        super().__init__()
        # Logging
        self._logger.debug('Instance of %s created: %s',
                           self.__class__.__name__, self.id)
        # Device attributes
        self.config = None  # Access to configuration INI file
        self.devices = {}  # List of processed proxy devices
        # Device parameters

    @property
    def id(self):
        name = os.path.splitext(__name__)[0]
        id = name.split('_')[1]
        return id

###############################################################################
# MQTT actions
###############################################################################
    def _setup_mqtt(self):
        """Define MQTT management."""
        self.mqtt_client = modMqtt.MqttBroker(
            clientid=self.id,
            connect=self._cbMqtt_on_connect,
            disconnect=self._cbMqtt_on_disconnect,
            subscribe=self._cbMqtt_on_subscribe,
            message=self._cbMqtt_on_message,
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

    def _cbMqtt_on_connect(self, client, userdata, flags, rc):
        """Process actions when the broker responds to a connection request.

        Arguments
        ---------
        client : object
            MQTT client instance for this callback.
        userdata
            The private user data.
        flags : dict
            Response flags sent by the MQTT broker.
        rc : int
            The connection result (result code).

        See Also
        --------
        gbj_sw.mqtt._on_connect()
            Description of callback arguments for proper utilizing.

        """
        if rc == 0:
            msg = f'Connected to {self.mqtt_client}: {userdata} ({rc=})'
            self._logger.debug(msg)
        else:
            errmsg = f'Connection to MQTT broker failed: {userdata} ({rc=})'
            self._logger.error(errmsg)

    def _cbMqtt_on_disconnect(self, client, userdata, rc):
        """Process actions when the client disconnects from the broker.

        Arguments
        ---------
        client : object
            MQTT client instance for this callback.
        userdata
            The private user data.
        rc : int
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

    def _cbMqtt_on_subscribe(self, client, userdata, mid, granted_qos):
        """Process actions when the broker responds to a subscribe request.

        Arguments
        ---------
        client : object
            MQTT client instance for this callback.
        userdata
            The private user data.
        mid : int
            The message ID from the subscribe request.
        granted_qos : int
            The list of integers that give the QoS level the broker has granted
            for each of the different subscription requests.

        """
        pass

    def _cbMqtt_on_message(self, client, userdata, message):
        """Process actions when a non-filtered message has been received.

        Arguments
        ---------
        client : object
            MQTT client instance for this callback.
        userdata
            The private user data.
        message : MQTTMessage object
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
        # Start all devices
        for _, device in self.devices.items():
            device.mqtt_client = self.mqtt_client
            device.begin()

    def finish(self):
        # Stop all devices plugins
        for _, device in self.devices.items():
            device.finish()
        self.publish_status(modIot.Status.OFFLINE)
        self.mqtt_client.disconnect()
        super().finish()
