# -*- coding: utf-8 -*-
"""Plugin module representing the cooling fan of the server.

- The module receives temperature percentage from MQTT broker and controls
  cooling fan according to it immidiatelly.

- The plugin represents the cooling fan directly, i.e., is able to control it
  directly with GPIO pins.

- The plugin receives commands for
  - publishing status
  - turning on and off the fan and for toggling it

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

# Custom library modules
from gbj_sw import iot as modIot


class Device(modIot.Plugin):
    """Plugin class."""

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(' '.join([__name__, __version__]))

    @property
    def id(self):
        return 'sfan'
