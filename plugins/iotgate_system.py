# -*- coding: utf-8 -*-
"""Plugin module for processing SoC events, mostly system temperature
 measurement.

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
import os

# Custom library modules
from gbj_sw import iot as modIot


class device(modIot.Plugin):
    """Plugin class."""

    def __init__(self):
        super().__init__()
        self._logger.debug('Instance of %s created: %s',
                           self.__class__.__name__, self.id)

    @property
    def id(self):
        name = os.path.splitext(__name__)[0]
        id = name.split('_')[1]
        return id
