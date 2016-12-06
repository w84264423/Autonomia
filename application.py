#!/usr/bin/env python
"""
  Cloud connected autonomous RC car.

  Copyright 2016 Visible Energy Inc. All Rights Reserved.
"""
__license__ = """
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import time
import json
import serial
import string
import sys
import copy
import signal
import subprocess
import pdb

# ---------------------
import utils
from cometalib import CometaClient
from runtime import Runtime
from gpslib import GPS
import api
from controller import RCVehicle

def signal_handler(signum, frame):
    sys.exit(0)

def main(argv):
  signal.signal(signal.SIGINT, signal_handler)

  Runtime.init_runtime()
  syslog = Runtime.syslog

  # Read configuration
  config = Runtime.read_config()
  if config == None:
    # error reading configuration file
    syslog("(FATAL) Error reading configuration file. Exiting.")
    return
  verbose = config['app_params']['verbose']
  syslog("Configuration: %s" % json.dumps(config))

  # Connect to GPS 
  if 'gps' in config:
    gps = GPS()
    ret = gps.connect(config['gps']['serial'], config['gps']['speed'])
    if ret:
      syslog("Connected to GPS.")
    else:
      gps = None
      syslog("Error connecting to GPS on % s. Disabling." % config['gps']['serial'])

  # Connect the device to Cometa
  cometa_server = config['cometa']['server']
  cometa_port = config['cometa']['port']
  application_id = config['cometa']['app_key']
  # use the machine's MAC address as Cometa device ID
  device_id = Runtime.get_serial()

  # Instantiate a Cometa object
  com = CometaClient(cometa_server, cometa_port, application_id, config['cometa']['ssl'])
  com.debug = config['app_params']['debug']
  # bind the message_handler() callback
  com.bind_cb(api.message_handler)

  # Attach the device to Cometa
  ret = com.attach(device_id, "Autonomia")
  if com.error != 0:
      print "(FATAL) Error in attaching to Cometa.", com.perror()
      sys.exit(2)

  # Get the timestamp from the server
  try:
      ret_obj = json.loads(ret)
  except Exception, e:
      print "(FATAL) Error in parsing the message returned after attaching to Cometa. Message:", ret
      sys.exit(2)

  # The server returns an object like: {"msg":"200 OK","heartbeat":60,"timestamp":1441405206}
  syslog("Device \"%s\" attached to Cometa. Server timestamp: %d" % (device_id, ret_obj['timestamp']))
  if com.debug:
      print "Server returned:", ret

  # create an empty telemetry file
  s = 'echo > /tmp/meta.txt'
  subprocess.check_call(s, shell=True)

  car = RCVehicle(config, syslog)
  # Start the vehicle with default training mode 
  car.start()

  last_second, last_telemetry = 0, 0
  telemetry_period = config['app_params']['telemetry_period']

  while car.state:
    now = time.time()

    # Per second loop
    if 1 < now - last_second:
      if config['app_params']['verbose']: print "GPS readings", gps.readings
      # update GPS readings
      car.readings = copy.deepcopy(gps.readings)
      last_second = time.time()

    # Send telemetry data
    if telemetry_period < now - last_telemetry: 
      msg = car.telemetry()
      if com.send_data(str(msg)) < 0:
          syslog("Error in sending telemetry data.")
      else:
          if com.debug:
              syslog("Sending telemetry data %s " % msg)

    time.sleep(1)

if __name__ == '__main__':
  main(sys.argv[1:])