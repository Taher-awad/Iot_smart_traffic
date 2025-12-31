import time
import json
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

import os

# Config (Same as traffic_gateway.py)
ENDPOINT = "a23rgceujjdkf1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "Command_Tester"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "../config")

PATH_TO_CERT = os.path.join(CONFIG_DIR, "certificate.pem.crt")
PATH_TO_KEY = os.path.join(CONFIG_DIR, "private.pem.key")
PATH_TO_ROOT = os.path.join(CONFIG_DIR, "AmazonRootCA1.pem")

mqtt_client = AWSIoTMQTTClient(CLIENT_ID)
mqtt_client.configureEndpoint(ENDPOINT, 8883)
mqtt_client.configureCredentials(PATH_TO_ROOT, PATH_TO_KEY, PATH_TO_CERT)

print(f"Connecting to AWS IoT Core at {ENDPOINT}...")
mqtt_client.connect()
print("Connected!")

# Command Payload
# Forces Lane 2 (South->North) to be Green for 10 seconds
command = {
    "lane": 2,
    "duration": 10000
}
topic = "traffic/INT_WEB/control"

print(f"Sending Command to {topic}: {command}")
mqtt_client.publish(topic, json.dumps(command), 1)

print("Command Sent! Check your Digital Twin.")
mqtt_client.disconnect()
