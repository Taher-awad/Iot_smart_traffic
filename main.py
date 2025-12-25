import paho.mqtt.client as mqtt
import json
import threading
import time

# --- CONFIG ---
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC_WILDCARD = "traffic/+/logs"

# --- KNOWN UNITS ---
known_intersections = set()

# --- COLORS ---
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

def on_connect(client, userdata, flags, rc):
    print(f"{GREEN}[SYSTEM] Dashboard Online. Scanning for Units...{RESET}")
    client.subscribe(TOPIC_WILDCARD)

def on_message(client, userdata, msg):
    try:
        # Topic format: traffic/INT_8A2F/logs
        topic_parts = msg.topic.split("/")
        unit_id = topic_parts[1]
        
        # New Unit Discovery Logic
        if unit_id not in known_intersections:
            known_intersections.add(unit_id)
            print(f"\n{MAGENTA}========================================{RESET}")
            print(f"{MAGENTA}   NEW UNIT DETECTED: {unit_id}   {RESET}")
            print(f"{MAGENTA}========================================{RESET}\n")
            print(f"{YELLOW}Input Command:{RESET} ", end="", flush=True)

        payload = msg.payload.decode()
        
        # Filter noise: Only show important logs
        if "ONLINE" in payload:
            print(f"{GREEN}[{unit_id} BOOT]{RESET} {payload}")
        elif "Fast Switch" in payload:
            print(f"{YELLOW}[{unit_id} ALERT]{RESET} {payload}")
        elif "OVERRIDE" in payload:
            print(f"{RED}[{unit_id} CMD]{RESET} {payload}")
        # Uncomment below to see every green light change
        # else: print(f"[{unit_id}] {payload}")

    except Exception as e:
        pass

def command_loop(client):
    while True:
        print(f"\n{CYAN}Active Units: {list(known_intersections)}{RESET}")
        print("Command Syntax: override <UNIT_ID> <LANE> <TIME>")
        
        cmd = input(f"{YELLOW}Input Command:{RESET} ")
        parts = cmd.split()
        
        if len(parts) == 4 and parts[0] == "override":
            target = parts[1]
            if target not in known_intersections:
                print(f"{RED}[ERROR] Unit '{target}' not found yet.{RESET}")
                continue

            try:
                lane = int(parts[2])
                dur = int(parts[3])
                
                topic = f"traffic/{target}/control"
                payload = json.dumps({"lane": lane, "time": dur})
                
                client.publish(topic, payload)
                print(f"{GREEN}>>> Command Sent to {target}{RESET}")
            except:
                print("Invalid numbers.")
        else:
            print("Unknown command.")

# --- MAIN ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

thread = threading.Thread(target=client.loop_forever)
thread.daemon = True
thread.start()

command_loop(client)