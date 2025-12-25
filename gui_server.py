import http.server
import socketserver
import json
import urllib.parse
import threading
import time
import webbrowser
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# --- AWS CONFIG ---
AWS_ENDPOINT = "a23rgceujjdkf1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "WebControlPanel"
PATH_TO_CERT = "certificate.pem.crt"
PATH_TO_KEY = "private.pem.key"
PATH_TO_ROOT = "root-CA.crt"

TOPIC_LOGS = "traffic/+/logs"
TOPIC_GATEWAY_LOGS = "traffic/gateway/logs"

# --- GLOBAL STATE ---
devices = {'INT_WEB'} # Pre-populate
mqtt_client = None

# --- MQTT SETUP ---
def on_message(client, userdata, msg):
    try:
        parts = msg.topic.split("/")
        if len(parts) >= 2:
            device_id = parts[1]
            if device_id not in devices:
                devices.add(device_id)
                print(f"[DISCOVERY] New Device: {device_id}")
    except:
        pass

def start_mqtt():
    global mqtt_client
    mqtt_client = AWSIoTMQTTClient(CLIENT_ID)
    mqtt_client.configureEndpoint(AWS_ENDPOINT, 8883)
    mqtt_client.configureCredentials(PATH_TO_ROOT, PATH_TO_KEY, PATH_TO_CERT)
    
    print("[MQTT] Connecting to AWS...")
    mqtt_client.connect()
    print("[MQTT] Connected!")
    
    mqtt_client.subscribe(TOPIC_LOGS, 1, on_message)
    mqtt_client.subscribe(TOPIC_GATEWAY_LOGS, 1, on_message)

# --- WEB SERVER ---
PORT = 8090

class ControlHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # API: Get Devices
        if parsed.path == "/devices":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(list(sorted(devices))).encode())
            return

        # API: Send Command
        if parsed.path == "/override":
            # /override?target=INT_WEB&lane=1&duration=10
            query = urllib.parse.parse_qs(parsed.query)
            target = query.get('target', [None])[0]
            lane = query.get('lane', [None])[0]
            duration = query.get('duration', ['10'])[0]

            if target and lane:
                topic = f"traffic/{target}/control"
                payload = json.dumps({
                    "lane": int(lane),
                    "duration": int(duration) * 1000
                })
                mqtt_client.publish(topic, payload, 1)
                print(f"[CMD] Sent Override -> {target} Lane {lane}")
                
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing params")
            return

        # Serve Dashboard (embedded HTML)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>IoT Traffic Control</title>
                <style>
                    body { font-family: 'Segoe UI', sans-serif; background: #222; color: #fff; text-align: center; padding: 20px; }
                    .card { background: #333; padding: 20px; margin: 10px auto; width: 350px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
                    select, input, button { box-sizing: border-box; width: 100%; padding: 10px; margin: 5px 0; border-radius: 5px; border: none; font-size: 16px; }
                    button { background: #e74c3c; color: white; cursor: pointer; font-weight: bold; transition: 0.2s; }
                    button:hover { background: #c0392b; transform: scale(1.02); }
                    h1 { color: #f1c40f; margin-bottom: 20px; }
                    .info { font-size: 14px; color: #aaa; margin-top: 5px; min-height: 20px; }
                    
                    /* Green styling for refresh */
                    button.refresh { background: #27ae60; }
                    button.refresh:hover { background: #2ecc71; }
                    
                    .manual-add { display: flex; gap: 5px; }
                    .manual-add input { width: 70%; }
                    .manual-add button { width: 30%; background: #3498db; }
                </style>
            </head>
            <body>
                <h1>🚦 IoT Traffic Command Center</h1>
                
                <div class="card">
                    <h3>1. Select Intersection</h3>
                    <select id="deviceSelect">
                        <option>Loading...</option>
                    </select>
                    
                    <div class="manual-add">
                        <input type="text" id="manualId" placeholder="Or type ID (e.g. INT_ESP32)">
                        <button onclick="addManual()">Add</button>
                    </div>
                    
                    <button class="refresh" onclick="fetchDevices()">🔄 Refresh List</button>
                </div>

                <div class="card">
                    <h3>2. Override Configuration</h3>
                    <label>Target Lane (0-3)</label>
                    <select id="laneSelect">
                        <option value="0">Lane 0 (Right - D12/D13)</option>
                        <option value="1">Lane 1 (Down - D27/D14)</option>
                        <option value="2">Lane 2 (Left - D25/D26)</option>
                        <option value="3">Lane 3 (Up - D32/D33)</option>
                    </select>
                    
                    <label>Duration (Seconds)</label>
                    <input type="number" id="durationInput" value="10" min="5" max="60">
                    
                    <button onclick="sendOverride()">🚨 SEND EMERGENCY OVERRIDE 🚨</button>
                    <div id="status" class="info">Ready</div>
                </div>

                <script>
                    async function fetchDevices() {
                        try {
                            const res = await fetch('/devices');
                            const devices = await res.json();
                            const sel = document.getElementById('deviceSelect');
                            const current = sel.value;
                            
                            sel.innerHTML = '';
                            if(devices.length === 0) {
                                sel.innerHTML = '<option>No devices found...</option>';
                            } else {
                                devices.forEach(d => {
                                    const opt = document.createElement('option');
                                    opt.value = d;
                                    opt.innerText = d;
                                    sel.appendChild(opt);
                                });
                                if(current && devices.includes(current)) sel.value = current;
                            }
                        } catch(e) { console.error(e); }
                    }

                    async function addManual() {
                        const id = document.getElementById('manualId').value.trim();
                        if(id) {
                            const sel = document.getElementById('deviceSelect');
                            const opt = document.createElement('option');
                            opt.value = id;
                            opt.innerText = id;
                            sel.appendChild(opt);
                            sel.value = id;
                            // Also add to server list visually (hack) or actually pushing not allowed via POST yet
                            // Just local is fine for user
                        }
                    }

                    async function sendOverride() {
                        const target = document.getElementById('deviceSelect').value;
                        const lane = document.getElementById('laneSelect').value;
                        const duration = document.getElementById('durationInput').value;
                        const status = document.getElementById('status');
                        const btn = document.querySelector('button[onclick="sendOverride()"]');

                        if(!target || target.includes('No devices') || target.includes('Loading')) {
                            alert('Please select a valid device!');
                            return;
                        }

                        status.innerText = "Sending Command...";
                        status.style.color = "#f1c40f";
                        btn.disabled = true;
                        
                        try {
                            const res = await fetch(`/override?target=${target}&lane=${lane}&duration=${duration}`);
                            if(res.ok) {
                                status.innerText = `✅ Signal Sent to ${target}!`;
                                status.style.color = "#2ecc71";
                            } else {
                                status.innerText = "❌ Error sending command.";
                                status.style.color = "#e74c3c";
                            }
                        } catch(e) {
                             status.innerText = "❌ Network Error.";
                        }
                        
                        setTimeout(() => {
                            status.innerText = "Ready";
                            status.style.color = "#aaa";
                            btn.disabled = false;
                        }, 3000);
                    }

                    // Auto-load
                    setInterval(fetchDevices, 2000);
                    fetchDevices();
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
            return
        
        # Fallback
        self.send_error(404)

def run_server():
    print(f"[WEB] Control Panel running at http://localhost:{PORT}")
    with socketserver.TCPServer(("", PORT), ControlHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=start_mqtt, daemon=True)
    t.start()
    
    # Open browser automatically
    webbrowser.open(f"http://localhost:{PORT}")
    
    run_server()
