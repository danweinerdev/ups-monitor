#!/usr/bin/env python

import errno
import os
import sys

pkgPath = os.path.realpath(os.path.join(__file__, os.pardir, os.pardir))
if os.path.exists(os.path.join(pkgPath, 'monitor-lib')):
    sys.path.insert(0, os.path.join(pkgPath, 'monitor-lib'))

from monitor.lib import Command, ConversionFailure, Execute, Metric, Result


def ProcessUps(pipeline, ups, config, logger=None):
    command = []
    if 'command' in config:
        command.extend(config['command'].split())
    else:
        command.append('/usr/bin/upsc')
    if not os.path.isabs(command[0]):
        command[0] = os.path.join(os.getcwd(), command[0])
    command.append(ups)

    try:
        result, output = Command(command, cwd=os.getcwd())
    except OSError as e:
        if e.errno == errno.ENOENT:
            if logger:
                logger.error('Unable to execute command: {}'.format(' '.join(command)))
            return False
        raise

    if result != 0:
        if logger:
            logger.error("upsc call for '{}' returned: {}".format(ups, result))
        return True

    for line in output:
        line = line.decode('utf-8')
        try:
            key, value = line.split(':')
        except ValueError:
            continue
        if key not in config['fields']:
            continue
        try:
            pipeline(Metric(ups, key, value.strip()))
        except ConversionFailure:
            if logger:
                logger.error("Failed to convert value '{}' for metric '{}'"
                    .format(value.strip(), key))

    return True


def Main(config, logger, pipeline):
    success = True
    for ups, cfg in config.items():
        if ProcessUps(pipeline, ups, cfg, logger=logger):
            success = False
    return Result.CANCEL if success else Result.FAILURE


if __name__ == "__main__":
     Execute(Main, 'ups')
