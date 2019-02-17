#!/usr/bin/env python

import argparse
from ConfigParser import ConfigParser
from datetime import datetime
from influxdb import InfluxDBClient
import logging
from logging import StreamHandler
from logging.handlers import TimedRotatingFileHandler
import os
import signal
import subprocess
import sys
import time
import threading

logger = logging.getLogger('nut.monitor')


class NutMonitorError(Exception):
    message = 'Whoops! An error occurred'

    def __init__(self, message=None):
        self.message = message or self.message


class ConfigError(NutMonitorError):
    message = 'A configuration error occurred'


def ConvertBoolean(value):
    if value.lower() in ['yes', '1', 'true']:
        return True
    if value.lower() in ['no', '0', 'false']:
        return False
    return None


def ConvertValue(value):
    try:
        v = float(value.strip())
        if '.' in value:
            return v
        return int(v)
    except (TypeError, ValueError):
        if ConvertBoolean(value.strip()) is None:
            return value.strip()
        return ConvertBoolean(value.strip())


def DropDescriptors():
    for fd in range(1, 3):
        try:
            os.close(fd)
        except (IOError, OSError):
            pass


def Execute(command, workingDirectory=None):
    try:
        with open('/dev/null', 'wb') as devnull:
            process = subprocess.Popen(command,
                cwd=workingDirectory,
                stdout=subprocess.PIPE,
                stderr=devnull,
                bufsize=1)

            output = []
            while True:
                if process.poll() is not None:
                    break
                for line in iter(process.stdout.readline, b''):
                    if len(line.strip()) > 0:
                        output.append(line.strip())
    except KeyboardInterrupt:
        pass
    except OSError:
        raise

    return process.poll(), output


def LoadConfiguration(configFile):
    parser = ConfigParser()
    with open(configFile, 'rb') as handle:
        parser.readfp(handle)

    if not parser.has_section('influx'):
        raise ConfigError('Invalid config file: %s' % args.config)

    config = {'influx': {}, 'ups': {}}

    influxRequiredFields = ['database', 'ups', 'server']
    for field in influxRequiredFields:
        if not parser.has_option('influx', field):
            raise ConfigError('Invalid influx configuration: Missing required field: %s' % field)

    allowedInfluxFields = ['database', 'port', 'server', 'ssl', 'verify']
    for field in allowedInfluxFields:
        if parser.has_option('influx', field):
            config['influx'][field] = ConvertValue(parser.get('influx', field))

    config['influx']['ups'] = parser.get('influx', 'ups', '').split()
    if len(config['influx']['ups']) == 0:
        raise ConfigError("No UPS configured")

    upsRequiredFields = ['fields', 'tags']

    for value in config['influx']['ups']:
        if not parser.has_section(value):
            raise ConfigError('No configuration for UPS: %s' % value)
        for field in upsRequiredFields:
            if not parser.has_option(value, field):
                raise ConfigError("Invalid ups configuration for '%s': Missing required field: %s" % \
                    (value, field))

        fields = parser.get(value, 'fields', '')
        tags = parser.get(value, 'tags', '')

        config['ups'][value] = {'tags': {}, 'fields': []}
        for tag in tags.split():
            try:
                k, v = tag.split('=')
            except ValueError:
                raise ConfigError("Invalid tag '%s' for UPS: %s" % (tag, value))
            config['ups'][value]['tags'][k] = v.strip()

        for field in fields.split():
            if not parser.has_section(field):
                raise ConfigError("Invalid field set '%s' for UPS: %s" % (field, value))
            if not parser.has_option(field, 'fields'):
                raise ConfigError('Malformed field configuration: %s' % field)
            sectionFields = parser.get(field, 'fields', '')
            if len(sectionFields) == 0:
                raise ConfigError('No fields specified for field set: %s' % field)
            config['ups'][value]['fields'].extend(sectionFields.split())
    return config


def ProcessUps(influx, ups, config):
    fields = config['fields']
    result, output = Execute(['upsc', ups])

    if result != 0:
        logger.error('upsc called returned: %d', result)
        return False

    timeStamp = TimeStamp()
    points = []

    for line in output:
        try:
            key, value = line.split(':')
        except ValueError:
            continue
        if key not in fields:
            continue
        points.append({
            'measurement': key.replace('.', '_'),
            'tags': config['tags'],
            'time': timeStamp,
            'fields': {'value': ConvertValue(value.strip())}})

    start = time.time()
    influx.write_points(points, time_precision='ms')
    stop = time.time()

    logger.debug("Uploaded '%d' metrics in %dms",
        len(points), stop - start)
    return True


def SetupLogging(args):
    if args.logfile is not None:
        handler = TimedRotatingFileHandler(
            args.logfile,
            backupCount=3,
            when='midnight')
    else:
        handler = StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


def TimeStamp(now=None):
    now = now or datetime.utcnow()
    return now.strftime('%Y-%m-%dT%H:%M:%SZ')


def Main(args):
    event = threading.Event()
    interval = (args.interval > 0)
    SetupLogging(args)

    if interval:
        def ShutdownHandler(sig, sigframe):
            logger.info('Signal received: %d', sig)
            if sig in [signal.SIGINT, signal.SIGTERM]:
                event.set()

        signal.signal(signal.SIGINT, ShutdownHandler)
        signal.signal(signal.SIGTERM, ShutdownHandler)
        if args.logfile is not None:
            DropDescriptors()

    if not os.path.isfile(args.config):
        logger.error('Config file not found: %s', args.config)
        return False

    # Load the configuration

    try:
        config = LoadConfiguration(args.config)
    except ConfigError as e:
        logger.error(e.message)
        return False

    # Start the InfluxDB client

    influx = InfluxDBClient(
        host=config['influx']['server'],
        port=config['influx']['port'],
        ssl=config['influx']['ssl'],
        verify_ssl=config['influx']['verify'],
        database=config['influx']['database'])

    logger.info('Successfully connected to InfluxDB: %s://%s:%d/%s',
        'https' if config['influx']['ssl'] else 'http',
        config['influx']['server'],
        config['influx']['port'],
        config['influx']['database'])

    # Execute the process for each configured UPS

    try:
        while True:
            for ups, configuration in config['ups'].items():
                if not ProcessUps(influx, ups, configuration):
                    logger.error('Failed to execute for UPS: %s', ups)
                    return False
            if event.is_set():
                break

            # TODO Update this sleep to a select-notify
            time.sleep(float(args.interval))
    finally:
        try:
            influx.close()
        except:
            pass

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser('nut-monitor')
    parser.add_argument('--config', '-c', required=True,
        help='Path to the config file')

    parser.add_argument('--interval', '-i', default=0, required=False,
        help='Poll interval between checking for changes (in seconds).')
    parser.add_argument('--log-file', '-l', dest='logfile', required=False,
        help='Path to the log file.')

    args = parser.parse_args()
    if not Main(args):
        sys.exit(1)
