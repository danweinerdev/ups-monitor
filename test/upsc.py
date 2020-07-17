#!/usr/bin/env python

import argparse
import hashlib
import os
import random

options = [
    ('driver.parameter.product', 'str'),
    ('input.transfer.high', 'int', 0, 100),
    ('input.transfer.low', 'int', 0, 100),
    ('input.voltage', 'int', 115, 125),
    ('input.voltage.nominal', 'int', 115, 125),
    ('output.voltage', 'float', 115.0, 125.0),
    ('battery.charge', 'int', 0, 100),
    ('battery.charge.low', 'int', 20, 30),
    ('battery.charge.warning', 'int', 30, 40),
    ('battery.runtime', 'int', 0, 60),
    ('battery.runtime.low', 'int', 0, 60),
    ('battery.voltage', 'float', 115.0, 125.0),
    ('battery.voltage.nominal', 'int', 115, 125),
    ('ups.beeper.status', 'str', '0'),
    ('ups.load', 'int', 0, 400),
    ('ups.status', 'str', '0'),
]

parser = argparse.ArgumentParser('upsc')
parser.add_argument('--random', '-r', action='store_true', default=False,
    help='Randomize the exit code for success or failure')
parser.add_argument('ups', help='UPS name to return for model value')

args = parser.parse_args()

if args.random:
    if random.randint(1, 10) == random.randint(1, 10):
        exit(1)


def GenerateValue(args):
    if args[0] == 'int':
        if len(args) == 3:
            return random.randint(args[1], args[2])
        elif len(args) == 2:
            return random.randint(0, args[1])
    elif args[0] == 'float':
        if len(args) == 3:
            return float(random.randint(args[1] * 10, args[2] * 10)) / 10
        elif len(args) == 2:
            return float(random.randint(0, args[1] * 10)) / 10
    elif args[0] == 'str':
        if len(args) == 2:
            return args[1]
        else:
            return str(hashlib.md5(os.urandom(128)).hexdigest())
    raise RuntimeError('Unsupported value generator: {}'.format(args[0]))


values = []
try:
    for option in options:
        values.append('{}: {}'.format(option[0], GenerateValue(option[1:])))
except Exception as e:
    exit(2)

for value in values:
    print(value)
print('ups.model: {}'.format(args.ups))
exit(0)
