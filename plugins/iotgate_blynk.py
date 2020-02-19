# -*- coding: utf-8 -*-
"""Plugin module representing the cloud service Blynk for mobile apps.

- The module receives data from several MQTT topics and immediatelly sends it
  to a mobile application.
- The module receives data from a mobile application and immediatelly sends it
  to an appropriate MQTT topic.

- The plugin receives commands
  - publish status

- The plugin receives data from MQTT broker
  - SoC temperature in centigrades from plugin `server`.
  - Activity status of the cooling fan from plugin 'sfan'. The plugin forwards
    published fan status to a mobile application.

- The plugin receives data from a mobile application
  - Command for turning cooling fan controlled by plugin 'sfan' ON or OFF.
    The plugin forwards fan command to appropriate MQTT topic.

 """
__version__ = '0.2.0'
__status__ = 'Beta'
__author__ = 'Libor Gabaj'
__copyright__ = 'Copyright 2020, ' + __author__
__credits__ = [__author__]
__license__ = 'MIT'
__maintainer__ = __author__
__email__ = 'libor.gabaj@gmail.com'

# Standard library modules
import logging
from enum import Enum
from typing import Optional, NoReturn

# Custom library modules
from gbj_sw import iot as modIot
import BlynkLib


class Device(modIot.Plugin):
    """Plugin class."""

    class Parameter(Enum):
        """Enumeration of plugin parameters for MQTT publishing topics."""
        TEMPERATURE = 'temp'
        FAN = 'cfan'

    class VirtualPin(Enum):
        """Enumeration of virtual pins used by the plugin."""
        TEMPERATURE = 1
        FAN = 3

    class Source(Enum):
        """Enumeration of depending plugins parameters."""
        TEMPERATURE_SYSTEM_DID = 'server'
        COOLING_FAN_DID = 'sfan'

    class CloudConfig(Enum):
        """Configuration parameters for INI file."""
        SECTION = 'Blynk'
        OPTION_API_KEY = 'blynk_api_key'
        HIGH = 1
        LOW = 0

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        self._blynk = None
        # Device parameters
        self.set_param(self.get_vpin(self.VirtualPin.TEMPERATURE),
                       self.Parameter.TEMPERATURE,
                       modIot.Measure.GPIO)
        self.set_param(self.get_vpin(self.VirtualPin.FAN),
                       self.Parameter.FAN,
                       modIot.Measure.GPIO)

    @property
    def did(self):
        """Device identifier."""
        return modIot.get_did(__name__)

    def get_vpin(self, vpin: Enum) -> str:
        """Compose virtual pin string from enumeration item."""
        return 'V' + str(vpin.value)

###############################################################################
# Cloud actions
###############################################################################
    def _setup_cloud(self) -> bool:
        """Define cloud management parameters and connect to it.

        Returns
        -------
        Flag about successful connection to the cloud.

        """
        if self._blynk:
            return True
        token = self.config.option(self.CloudConfig.OPTION_API_KEY.value,
                                   self.CloudConfig.SECTION.value)
        try:
            self._blynk = BlynkLib.Blynk(token)
        except ValueError as errmsg:
            self._logger.error(errmsg)
            return False
        else:
            @self._blynk.on(self.get_vpin(self.VirtualPin.FAN))
            def _fan_button(value):
                """Handler for received fan button state from mobile app."""
                # Propagate button state to the MQTT broker as COMMAND
                sfan = self.devices[self.Source.COOLING_FAN_DID.value]
                topic = sfan.get_topic(modIot.Category.COMMAND)
                status = abs(int(value[0]))
                if status == self.CloudConfig.LOW.value:
                    message = modIot.Command.TURN_OFF.value
                elif status == self.CloudConfig.HIGH.value:
                    message = modIot.Command.TURN_ON.value
                log = modIot.get_log(message, modIot.Category.COMMAND)
                self._logger.debug(log)
                self.mqtt_client.publish(message, topic)
            return True

    def run(self) -> NoReturn:
        """Run loop function for communicating with the cloud."""
        if self._blynk:
            self._blynk.run()
            return True
        return False

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
        self._setup_cloud()
        self.publish_status()

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
                    # Send temperature to a mobile app
                    pin = self.VirtualPin.TEMPERATURE.value
                    if self._setup_cloud():
                        self._blynk.virtual_write(pin, temperature)
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
                log = f'Fan button set to {status=}'
                pin = self.VirtualPin.FAN.value
                value = None
                if status == modIot.Status.ACTIVE.value:
                    # Turn fan button ON in a mobile app
                    value = self.CloudConfig.HIGH.value
                elif status == modIot.Status.IDLE.value:
                    # Turn fan button OFF in a mobile app
                    value = self.CloudConfig.LOW.value
                if value is None:
                    log = f'Ignored fan {status=}'
                    self._logger.warning(log)
                elif self._setup_cloud():
                    self._blynk.virtual_write(pin, value)
                    self._logger.debug(log)
