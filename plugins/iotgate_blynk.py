# -*- coding: utf-8 -*-
"""Plugin module representing the cloud service Blynk for mobile apps.

- The module receives data from several MQTT topics and immediatelly sends it
  to a mobile application.
- The module receives data from a mobile application and immediatelly sends it
  to an appropriate MQTT topic.

- The plugin receives commands
  - publish status
  - reset plugin

- The plugin receives data from MQTT broker
  - SoC temperature in centigrades from plugin `server`.
  - Activity status of the cooling fan from plugin 'sfan'. The plugin forwards
    published fan status to a mobile application.

- The plugin receives data from a mobile application
  - Command for turning cooling fan controlled by plugin 'sfan' ON or OFF.
    The plugin forwards fan command to appropriate MQTT topic.

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
        TEMPERATURE = 'V1'
        FAN = 'V2'

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
        token = self.config.option(self.CloudConfig.OPTION_API_KEY.value,
                                   self.CloudConfig.SECTION.value)
        self._blynk = BlynkLib.Blynk(token)
        # Device parameters
        self.set_param(self.VirtualPin.TEMPERATURE,
                       self.Parameter.TEMPERATURE,
                       modIot.Measure.GPIO)
        self.set_param(self.VirtualPin.FAN,
                       self.Parameter.FAN,
                       modIot.Measure.GPIO)

    @property
    def did(self):
        """Device identifier."""
        return modIot.get_did(__name__)

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
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
                    value = self.CloudConfig.HIGH
                elif status == modIot.Status.IDLE.value:
                    # Turn fan button OFF in a mobile app
                    value = self.CloudConfig.LOW
                if value is None:
                    log = f'Ignored fan {status=}'
                    self._logger.warning(log)
                else:
                    self._blynk.virtual_write(pin, value)
                    self._logger.debug(log)


###############################################################################
# Blynk actions
###############################################################################
