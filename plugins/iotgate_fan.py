# -*- coding: utf-8 -*-
"""Plugin module representing the cooling fan of the server.

- The module receives temperature percentage from MQTT broker and controls
  cooling fan according to it immidiatelly.

- The plugin represents the cooling fan directly, i.e., is able to control it
  directly with GPIO pins.

- The plugin receives commands
  - publish status
  - reset plugin
  - turn on/off/toggle the cooling fan

- The plugin receives data
  - SoC temperature percentage from plugin `server`

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
from gbj_hw.orangepi import OrangePiOne as classPi


def fan_command(func):
    """Decorator for handling commands for the fan."""
    def _decorator(self):
        command = func(self)
        # Publish only at real command execution
        if command:
            self.set_param(self.activity, self.Parameter.ACTIVITY)
            self.publish_param(self.Parameter.ACTIVITY)
            log = f'Executed fan command {command.name}'
            self.logger.info(log)
    return _decorator


class Device(modIot.Plugin):
    """Plugin class."""

    class Parameter(Enum):
        """Enumeration of plugin parameters for MQTT publishing topics."""
        FAN = 'cfan'
        ACTIVITY = 'run'
        PERCENTAGE_ON = 'percon'
        PERCENTAGE_OFF = 'percoff'

    class Source(Enum):
        """Enumeration of depending plugins parameters."""
        TEMPERATURE_SYSTEM_DID = 'server'

    class GpioPin(Enum):
        """Utilized pins of the microcomputer."""
        FAN = 'PA13'

    class PercentageOn(Enum):
        """Parameters of temperature percentage for fan turning ON."""
        DEFAULT = 90.0
        MINIMUM = 80.0
        MAXIMUM = 95.0

    class PercentageOff(Enum):
        """Parameters of temperature percentage for fan turning OFF."""
        DEFAULT = 60.0
        MINIMUM = 50.0
        MAXIMUM = 75.0

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))
        self._percentage = None  # Cached received SoC temperature percentage
        # Initialize fan
        self._pi = classPi()  # Handler of microcomputer GPIO
        self._pi.pin_off(self.GpioPin.FAN.value)  # Fan pin to OUTPUT and LOW
        # Device parameters
        self.set_param(self.GpioPin.FAN.value,
                       self.Parameter.FAN,
                       modIot.Measure.GPIO)
        self.set_param(self.activity,
                       self.Parameter.ACTIVITY)
        self.set_param(self.percon,
                       self.Parameter.PERCENTAGE_ON,
                       modIot.Measure.VALUE)
        self.set_param(self.PercentageOn.DEFAULT.value,
                       self.Parameter.PERCENTAGE_ON,
                       modIot.Measure.DEFAULT)
        self.set_param(self.PercentageOn.MINIMUM.value,
                       self.Parameter.PERCENTAGE_ON,
                       modIot.Measure.MINIMUM)
        self.set_param(self.PercentageOn.MAXIMUM.value,
                       self.Parameter.PERCENTAGE_ON,
                       modIot.Measure.MAXIMUM)
        self.set_param(self.percoff,
                       self.Parameter.PERCENTAGE_OFF,
                       modIot.Measure.VALUE)
        self.set_param(self.PercentageOff.DEFAULT.value,
                       self.Parameter.PERCENTAGE_OFF,
                       modIot.Measure.DEFAULT)
        self.set_param(self.PercentageOff.MINIMUM.value,
                       self.Parameter.PERCENTAGE_OFF,
                       modIot.Measure.MINIMUM)
        self.set_param(self.PercentageOff.MAXIMUM.value,
                       self.Parameter.PERCENTAGE_OFF,
                       modIot.Measure.MAXIMUM)

    @property
    def did(self):
        """Device identifier."""
        return 'sfan'

    @property
    def logger(self):
        """Published logger object for loging from external decorators."""
        return self._logger

###############################################################################
# Fan actions
###############################################################################
    @property
    def activity(self) -> modIot.Status:
        """Current fan activity."""
        pin = self.GpioPin.FAN.value
        if self._pi.is_pin_input(pin):
            activity = modIot.Status.IDLE
        elif self._pi.is_pin_on(pin):
            activity = modIot.Status.ACTIVE
        elif self._pi.is_pin_off(pin):
            activity = modIot.Status.IDLE
        else:
            activity = modIot.Status.UNKNOWN
        return activity.value

    @property
    def percon(self) -> float:
        """Current temperature for turning fan ON in percentage."""
        val = self.get_param(self.Parameter.PERCENTAGE_ON,
                             modIot.Measure.VALUE,
                             self.PercentageOn.DEFAULT.value)
        return val

    @percon.setter
    def percon(self, percon: float):
        """Sanitize and set new turn ON temperature percentage."""
        try:
            old = self.percon
            new = float(percon or self.PercentageOn.DEFAULT.value)
            if old == new:
                raise ValueError
        except (ValueError, TypeError):
            pass
        else:
            # Sanitize new value
            new = min(max(abs(new), self.PercentageOn.MINIMUM.value),
                      self.PercentageOn.MAXIMUM.value)
            # Register new value
            self.set_param(new,
                           self.Parameter.PERCENTAGE_ON,
                           modIot.Measure.VALUE)
            # Publish new value
            self.publish_param(self.Parameter.PERCENTAGE_ON,
                               modIot.Measure.VALUE)
            # Apply new value
            self.fan_process()

    @property
    def percoff(self) -> float:
        """Current temperature for turning fan OFF in percentage."""
        val = self.get_param(self.Parameter.PERCENTAGE_OFF,
                             modIot.Measure.DEFAULT,
                             self.PercentageOff.DEFAULT.value)
        return val

    @percoff.setter
    def percoff(self, percoff: float):
        """Sanitize and set new turn OFF temperature percentage."""
        try:
            old = self.percoff
            new = float(percoff or self.PercentageOff.DEFAULT.value)
            if old == new:
                raise ValueError
        except (ValueError, TypeError):
            pass
        else:
            # Sanitize new value
            new = min(max(abs(new), self.PercentageOff.MINIMUM.value),
                      self.PercentageOff.MAXIMUM.value)
            # Register new period
            self.set_param(new,
                           self.Parameter.PERCENTAGE_OFF,
                           modIot.Measure.VALUE)
            # Publish new period
            self.publish_param(self.Parameter.PERCENTAGE_OFF,
                               modIot.Measure.VALUE)
            # Apply new period
            self.fan_process()

    @fan_command
    def fan_on(self) -> Optional[modIot.Command]:
        """Turn the fan ON if it is OFF."""
        pin = self.GpioPin.FAN.value
        if self._pi.is_pin_off(pin):
            self._pi.pin_on(pin)
            return modIot.Command.TURN_ON
        return None

    @fan_command
    def fan_off(self) -> Optional[modIot.Command]:
        """Turn the fan OFF if it is ON."""
        pin = self.GpioPin.FAN.value
        if self._pi.is_pin_on(pin):
            self._pi.pin_off(pin)
            return modIot.Command.TURN_OFF
        return None

    @fan_command
    def fan_toggle(self) -> modIot.Command:
        """Toggle the fan."""
        self._pi.pin_toggle(self.GpioPin.FAN.value)
        return modIot.Command.TOGGLE

    def fan_process(self) -> Optional[modIot.Command]:
        """Process recent good received temperature percentage from MQTT."""
        # Start cooling
        if self._percentage >= self.percon:
            return self.fan_on()
        # Stop cooling
        if self._percentage <= self.percoff:
            return self.fan_off()
        return None

###############################################################################
# General actions
###############################################################################
    def begin(self):
        super().begin()
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
            # Turn the fan ON
            if value == modIot.Command.TURN_ON.value:
                self.fan_on()
            # Turn the fan OFF
            if value == modIot.Command.TURN_OFF.value:
                self.fan_off()
            # Turn the fan toggle
            if value == modIot.Command.TOGGLE.value:
                self.fan_toggle()
            # Reset status
            if value == modIot.Command.RESET.value:
                self.percon = None
                self.percoff = None
                log = f'Device reset'
                self._logger.warning(log)
        # Change percentage ON
        if parameter == self.Parameter.PERCENTAGE_ON.value \
                and measure == modIot.Measure.VALUE.value:
            self.percon = value
            log = f'Turn ON temperature set to {self.percon}%'
            self._logger.warning(log)
        # Change percentage OFF
        if parameter == self.Parameter.PERCENTAGE_OFF.value \
                and measure == modIot.Measure.VALUE.value:
            self.percoff = value
            log = f'Turn OFF temperature set to {self.percoff}%'
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
        # Process data from plugin 'system'
        if device.did == self.Source.TEMPERATURE_SYSTEM_DID.value:
            # Process temperature percentage
            if parameter == device.Parameter.TEMPERATURE.value \
                    and measure == modIot.Measure.PERCENTAGE.value:
                try:
                    percentage = float(value)
                except (TypeError, ValueError):
                    log = f'Ignored invalid temperature percentage {value=}'
                    self._logger.warning(log)
                else:
                    self._percentage = percentage
                    log = f'Process temperature {percentage=}%'
                    self._logger.debug(log)
                    self.fan_process()
