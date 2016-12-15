#!/usr/bin/python
# coding=utf-8
import argparse
import base64
import hmac
import hashlib
import platform
import socket
import requests
import urllib
import json

# import Yoctopuce Pyhton library (installed form PyPI)
from yoctopuce.yocto_api import *
from yoctopuce.yocto_temperature import *
from yoctopuce.yocto_humidity import *
from yoctopuce.yocto_gps import *
from yoctopuce.yocto_latitude import *
from yoctopuce.yocto_longitude import *


class D2CMsgSender:
    API_VERSION = '2016-02-03'
    TOKEN_VALID_SECS = 10
    TOKEN_FORMAT = 'SharedAccessSignature sig=%s&se=%s&skn=%s&sr=%s'

    def __init__(self, device_id, iot_host, key):
        self.devicid = device_id
        self.iotHost = iot_host
        self.keyValue = key

    def _buildExpiryOn(self):
        return '%d' % (time.time() + self.TOKEN_VALID_SECS)

    def _buildIoTHubSasToken(self):
        resourceUri = '%s/devices/%s' % (self.iotHost, self.devicid)
        targetUri = resourceUri.lower()
        expiryTime = self._buildExpiryOn()
        toSign = '%s\n%s' % (targetUri, expiryTime)
        key = base64.b64decode(self.keyValue.encode('utf-8'))
        signature = urllib.quote(
            base64.b64encode(
                hmac.HMAC(key, toSign.encode('utf-8'), hashlib.sha256).digest()
            )
        ).replace('/', '%2F')
        return self.TOKEN_FORMAT % (signature, expiryTime, "", targetUri)

    def sendD2CMsg(self, message):
        sasToken = self._buildIoTHubSasToken()
        url = 'https://%s/devices/%s/messages/events?api-version=%s' % (self.iotHost, self.devicid, self.API_VERSION)
        r = requests.post(url, headers={'Authorization': sasToken}, data=message)
        return r.text, r.status_code


def send_sensor_values(azure_deviceId):
    tempSensor = YTemperature.FirstTemperature()
    humSensor = YHumidity.FirstHumidity()
    if tempSensor is None or humSensor is None:
        print("No Yocto-Meteo connected. Check your USB cable.")
        return
    while tempSensor.isOnline():
        temp = tempSensor.get_currentValue()
        humitdity = humSensor.get_currentValue()
        print('Send new value: temperature=%2.1f%s and humidity=%2.1f%s' % (
            temp, tempSensor.get_unit(), humitdity, humSensor.get_unit()))
        value_mesage = json.dumps({
            'DeviceID': azure_deviceId,
            'Temperature': temp,
            'Humidity': humitdity,
        })
        ret = d2cMsgSender.sendD2CMsg(value_mesage)
        if ret[1] != 204:
            print("unable to contact Azure Iot Hub:" + ret[0])
            return
        YAPI.Sleep(10000)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Yoctopuce device to Azure Iot Suite brigde.')
    parser.add_argument('deviceid', type=str,
                        help='The Device Id ')
    parser.add_argument('HostName', type=str,
                        help='The hostname of the Azure IoT Hub')
    parser.add_argument('AccessKey', type=str,
                        help='The access key of the device')
    args = parser.parse_args()
    errmsg = YRefParam()

    # Setup the API to use local USB devices
    if YAPI.RegisterHub("usb", errmsg) != YAPI.SUCCESS:
        sys.exit("init error" + errmsg.value)

    latitude = 0
    longitude = 0
    gps = YGps.FirstGps()
    if gps is not None:
        if gps.get_isFixed() != YGps.ISFIXED_TRUE:
            print("Wait for GPS fix."),
            w = 0
            while gps.get_isFixed() != YGps.ISFIXED_TRUE and w < 30:
                YAPI.Sleep(1000)
                w += 1
                print".",
        if gps.get_isFixed() == YGps.ISFIXED_TRUE:
            gps_serial = gps.get_module().get_serialNumber()
            ylatitude = YLatitude.FindLatitude(gps_serial + ".latitude")
            ylongitude = YLongitude.FindLongitude(gps_serial + ".longitude")
            latitude = ylatitude.get_currentValue() / 1000.0
            longitude = ylongitude.get_currentValue() / 1000.0
        else:
            print("unable to get GPS fix in 30 seconds")

    deviceid = args.deviceid
    host_name = args.HostName
    if not host_name.endswith(".azure-devices.net"):
        host_name += ".azure-devices.net"

    d2cMsgSender = D2CMsgSender(deviceid, host_name, args.AccessKey)
    machine = platform.machine()
    system = platform.system()
    print("GPS location is %f %f" % (latitude, longitude))
    deviceMetaData = {
        'ObjectType': 'DeviceInfo',
        'IsSimulatedDevice': 0,
        'Version': '1.0',
        'DeviceProperties': {
            'DeviceID': deviceid,
            'HubEnabledState': 1,
            'CreatedTime': '2016-12-12T20:28:55.5448990Z',
            'DeviceState': 'normal',
            'UpdatedTime': None,
            'Manufacturer': 'Yoctopuce',
            'ModelNumber': 'azure-iot-brige',
            'SerialNumber': socket.gethostname(),
            'FirmwareVersion': '1.0',
            'Platform': system,
            'Processor': machine,
            'InstalledRAM': '64 MB',
            'Latitude': latitude,
            'Longitude': longitude
        },
        'Commands': [],
        "Telemetry": [
            {
                "Name": "Temperature",
                "DisplayName": "Temperature",
                "Type": "double"
            },
            {
                "Name": "Lumosity",
                "DisplayName": "Lumosity",
                "Type": "double"
            },
            {
                "Name": "Humidity",
                "DisplayName": "Humidity",
                "Type": "double"
            }
        ]
    }
    # Senddevice metadata
    res = d2cMsgSender.sendD2CMsg(json.dumps(deviceMetaData))
    if res[1] != 204:
        print("unable to contact Azure Iot Hub:" + res[0])
        YAPI.FreeAPI()
        sys.exit()

    send_sensor_values(deviceid)
    YAPI.FreeAPI()
    print("exiting..")
