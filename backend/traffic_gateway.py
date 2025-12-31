import time
import json
import asyncio
import websockets
import threading
import paho.mqtt.client as mqtt
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

import os

# --- CONFIGURATION ---
# 1. AWS Config
AWS_ENDPOINT = "a23rgceujjdkf1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "TrafficGateway_Bridge"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "../config")

PATH_TO_CERT = os.path.join(CONFIG_DIR, "certificate.pem.crt")
PATH_TO_KEY = os.path.join(CONFIG_DIR, "private.pem.key")
PATH_TO_ROOT = os.path.join(CONFIG_DIR, "root-CA.crt")

# 2. Local Broker Config
LOCAL_BROKER = "localhost" 
LOCAL_PORT = 1883


# --- TOPICS ---
TOPIC_LOGS_IN = "traffic/+/logs"      
TOPIC_LOGS_OUT = "traffic/gateway/logs"
TOPIC_CMD_IN = "traffic/+/control"    # CHANGED: Listen to all device control commands

# --- AWS CONNECTION ---
print("[GATEWAY] Connecting to AWS IoT Core...")
aws_client = AWSIoTMQTTClient(CLIENT_ID)
aws_client.configureEndpoint(AWS_ENDPOINT, 8883)
aws_client.configureCredentials(PATH_TO_ROOT, PATH_TO_KEY, PATH_TO_CERT)
aws_client.connect()
print("[GATEWAY] AWS Connected!")

# --- WEB SOCKET BRIDGE ---
ws_clients = set()
ws_loop = None

async def ws_handler(websocket):
    ws_clients.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "log_publish":
                    # Forward to AWS as if it was a local device
                    topic = data.get("topic", "traffic/UNKNOWN/logs")
                    payload = data.get("payload", "")
                    
                    # Extract ID from topic "traffic/ID/logs"
                    parts = topic.split("/")
                    unit_id = parts[1] if len(parts) > 1 else "INT_WEB"
                    
                    print(f"[WS -> AWS] {unit_id}: {payload}")
                    
                    aws_payload = json.dumps({
                        "unit_id": unit_id,
                        "data": payload,
                        "timestamp": time.time()
                    })
                    aws_client.publish(TOPIC_LOGS_OUT, aws_payload, 1)
                    
            except Exception as e:
                print(f"[WS ERROR] {e}")

    except:
        pass
    finally:
        ws_clients.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(ws_clients)}")

async def start_ws_server():
    global ws_loop
    ws_loop = asyncio.get_running_loop()
    print("[WS] Starting WebSocket Server on port 8765...")
    # Add reuse_address to prevent "Address already in use" on restart
    async with websockets.serve(ws_handler, "0.0.0.0", 8765, reuse_address=True):
        await asyncio.Future()

def run_ws_thread():
    asyncio.run(start_ws_server())

ws_thread = threading.Thread(target=run_ws_thread, daemon=True)
ws_thread.start()

def broadcast_ws(data_dict):
    if not ws_clients: return
    msg = json.dumps(data_dict)
    if ws_loop:
        asyncio.run_coroutine_threadsafe(broadcast_to_all(msg), ws_loop)

async def broadcast_to_all(msg):
    if not ws_clients: return
    for ws in list(ws_clients):
        try:
            await ws.send(msg)
        except:
            pass

# --- CALLBACKS ---
def on_local_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload.decode()
        parts = topic.split("/")
        unit_id = parts[1] if len(parts) > 1 else "UNKNOWN"
        
        print(f"[LOCAL -> AWS] {unit_id}: {payload}")
        
        broadcast_ws({
            "type": "log",
            "unit_id": unit_id,
            "topic": topic,
            "data": payload
        })
        
        aws_payload = json.dumps({
            "unit_id": unit_id,
            "data": payload,
            "timestamp": time.time()
        })
        aws_client.publish(TOPIC_LOGS_OUT, aws_payload, 1)
        
    except Exception as e:
        print(f"Error forwarding: {e}")

def on_aws_message(client, userdata, msg):
    try:
        print(f"[AWS -> GATEWAY] Message on {msg.topic}")
        payload = json.loads(msg.payload.decode())
        
        # 1. Parse Target from Topic "traffic/ID/control"
        parts = msg.topic.split("/")
        target_unit = parts[1] if len(parts) > 1 else "UNKNOWN"
        
        # 2. Parse Command
        lane = payload.get("lane")
        duration = payload.get("duration", payload.get("time", 5000)) # Support both
        
        if lane is not None:
             print(f"[AWS -> LOCAL/WS] Override {target_unit} Lane {lane} for {duration}ms")
             
             # A. Forward to Local MQTT (for ESP32)
             # payload is already JSON, easy to forward
             local_client.publish(msg.topic, json.dumps({"lane": lane, "time": duration}))
             
             # B. Broadcast to Web Twin via WebSocket
             broadcast_ws({
                "type": "command",
                "target": target_unit,
                "lane": lane,
                "duration": duration
            })
            
    except Exception as e:
        print(f"Error parsing AWS command: {e}")

# --- LOCAL CONNECTION ---
local_client = mqtt.Client()
local_client.on_message = on_local_message

connected_local = False
while not connected_local:
    try:
        local_client.connect(LOCAL_BROKER, LOCAL_PORT, 60)
        connected_local = True
        print("[GATEWAY] Connected to Local Broker!")
    except Exception as e:
        print(f"[GATEWAY] Local Broker not found ({e}). AWS Connected. WS Active. Retrying Local in 5s...")
        time.sleep(5)

local_client.subscribe(TOPIC_LOGS_IN)
aws_client.subscribe(TOPIC_CMD_IN, 1, on_aws_message)

print("[GATEWAY] Bridge Active. Press Ctrl+C to stop.")
local_client.loop_forever()
