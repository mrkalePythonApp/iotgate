#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IoT gateway for processing messages from/to MQTT clients as a IoT devices.

Script provides following functionalities:

- Script acts as an MQTT client utilizing local MQTT broker ``mosquitto``
  for data exchange with outside environment.
- Script receives data from sensors managed by microcontrollers and process
  it and publishes it to cloud services.
- Script publishes received data and configuration data to the
  ``local MQTT broker``.
- Script sends commands through MQTT to microcontrollers in order to control
  them centrally.
- Script can receive commands through MQTT in order to change its behaviour
  during running.

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
import os
import sys
import argparse
import logging
from importlib import util as imp

# Third party modules
from gbj_sw import utils as modUtils
from gbj_sw import config as modConfig


###############################################################################
# Enumeration and parameter classes
###############################################################################
class Script:
    """Script parameters."""

    (fullname, basename, name, service) = (None, None, None, False)

class Actuator:
    """Objects of respective processors."""
    (cmdline, logger, gate) = (None, None, None)


###############################################################################
# Setup functions
###############################################################################
def setup_params():
    """Determine script operational parameters."""
    Script.fullname = os.path.splitext(os.path.abspath(__file__))[0]
    Script.basename = os.path.basename(__file__)
    Script.name = os.path.splitext(Script.basename)[0]
    Script.service = modUtils.check_service(Script.name)


def setup_cmdline():
    """Define command line arguments."""
    config_file = Script.fullname + '.ini'
    if modUtils.linux():
        log_folder = '/var/log'
    elif modUtils.windows():
        log_folder = modUtils.envdir('TEMP')
    # Plugins folder default
    plugin_folder = modUtils.envdir(Script.name.upper() + '_PLUGINS')

    parser = argparse.ArgumentParser(
        description='IoT gate and MQTT client, version '
        + __version__
    )
    # Position arguments
    parser.add_argument(
        'config',
        type=argparse.FileType('r'),
        nargs='?',
        default=config_file,
        help=f'Configuration INI file, default "{config_file}"'
    )
    # Options
    parser.add_argument(
        '-V', '--version',
        action='version',
        version=__version__,
        help='Current version of the script.'
    )
    parser.add_argument(
        '-v', '--verbose',
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        default='debug',
        help='Level of logging to the console.'
    )
    parser.add_argument(
        '-l', '--loglevel',
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        default='debug',
        help='Level of logging to a log file.'
    )
    parser.add_argument(
        '-d', '--logdir',
        default=log_folder,
        help=f'Folder of a log file, default "{log_folder}"'
    )
    parser.add_argument(
        '-p', '--plugindir',
        default=plugin_folder,
        help=f'Folder with plugins, default "{plugin_folder}"'
    )
    # Process command line arguments
    Actuator.cmdline = parser.parse_args()


def setup_logger():
    """Configure logging facility."""
    # Set logging to file for module and script logging
    log_file = '/'.join([Actuator.cmdline.logdir, Script.basename + '.log'])
    logging.basicConfig(
        level=getattr(logging, Actuator.cmdline.loglevel.upper()),
        format='%(asctime)s - %(levelname)-8s - %(name)s: %(message)s',
        filename=log_file,
        filemode='w'
    )
    # Set console logging
    formatter = logging.Formatter(
        '%(levelname)-8s - %(name)-20s: %(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, Actuator.cmdline.verbose.upper()))
    console_handler.setFormatter(formatter)
    Actuator.logger = logging.getLogger('{} {}'.format(Script.basename, __version__))
    Actuator.logger.addHandler(console_handler)
    Actuator.logger.info('Script started from file %s', os.path.abspath(__file__))


def setup_plugins():
    """Import all plugins."""
    plugins_path, _, module_files = next(os.walk(Actuator.cmdline.plugindir))
    # Import plugin modules
    devices = {}
    for module_file in module_files:
        # Plugin file name should be prefixed with script name
        if not module_file.startswith(Script.name + '_'):
            continue
        # Load plugin
        module_path = os.path.join(plugins_path, module_file)
        try:
            spec = imp.spec_from_file_location(module_file, module_path)
            plugin_module = imp.module_from_spec(spec)
            spec.loader.exec_module(plugin_module)
            plugin = plugin_module.Device()
            plugin_name = os.path.splitext(plugin_module.__name__)[0]
            plugin_version = plugin_module.__version__
            plugin_id = plugin.did
            devices[plugin_id] = plugin
            log = \
                f'Loaded plugin="{plugin_name}", version={plugin_version}' \
                f', did="{plugin_id}"'
            Actuator.logger.info(log)
        except Exception as errmsg:
            log = f'Cannot load plugin "{module_path}": {errmsg}'
            Actuator.logger.exception(log)
    # Put list of supported devices to application plugin
    if Script.name in devices:
        Actuator.gate = devices[Script.name]
        Actuator.gate.config = modConfig.Config(Actuator.cmdline.config)
        for name, plugin in devices.items():
            Actuator.gate.devices[name] = plugin
    else:
        log = f'No plugin for "{Script.basename}"'
        Actuator.logger.error(log)

def setup():
    """Global initialization."""
    msg = \
        f'Script runs as a ' \
        f'{"service" if Script.service else "program"}'
    Actuator.logger.info(msg)
    Actuator.gate.begin()


def loop():
    """Wait for keyboard or system exit."""
    try:
        Actuator.logger.info('Script loop started')
        while True:
            Actuator.gate.run()
        log = 'finished'
    except (KeyboardInterrupt, SystemExit):
        log = 'cancelled from keyboard'
    finally:
        Actuator.gate.finish()
        Actuator.logger.info(f'Script {log}')


def main():
    """Fundamental control function."""
    setup_params()
    setup_cmdline()
    setup_logger()
    setup_plugins()
    setup()
    loop()


if __name__ == "__main__":
    if modUtils.linux() and not modUtils.root():
        sys.exit('Script must be run as root')
    main()
