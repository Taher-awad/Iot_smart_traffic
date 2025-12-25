import tkinter as tk
from tkinter import ttk, messagebox
import json
import time
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import threading

# --- AWS CONFIG ---
AWS_ENDPOINT = "a23rgceujjdkf1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "TrafficControlPanel"
PATH_TO_CERT = "certificate.pem.crt"
PATH_TO_KEY = "private.pem.key"
PATH_TO_ROOT = "root-CA.crt"

TOPIC_LOGS = "traffic/+/logs"
TOPIC_GATEWAY_LOGS = "traffic/gateway/logs"

class TrafficControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IoT Traffic Control Center")
        self.root.geometry("600x450")
        
        # --- AWS Client ---
        self.aws_client = AWSIoTMQTTClient(CLIENT_ID)
        self.aws_client.configureEndpoint(AWS_ENDPOINT, 8883)
        self.aws_client.configureCredentials(PATH_TO_ROOT, PATH_TO_KEY, PATH_TO_CERT)
        
        self.devices = set()
        
        # --- UI LAYOUT ---
        self.create_widgets()
        
        # --- CONNECT ---
        self.connect_aws()

    def create_widgets(self):
        # 1. Header
        header = tk.Label(self.root, text="🚦 Traffic Emergency Control", font=("Arial", 16, "bold"))
        header.pack(pady=10)

        # 2. Main Frame
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 3. Device List (Left)
        left_frame = tk.LabelFrame(main_frame, text="Active Intersections")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        self.device_list = tk.Listbox(left_frame, height=15)
        self.device_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 4. Controls (Right)
        right_frame = tk.LabelFrame(main_frame, text="Override Controls")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        # Lane Selection
        tk.Label(right_frame, text="Target Lane (0-3):").pack(pady=5)
        self.lane_var = tk.StringVar(value="0")
        lane_combo = ttk.Combobox(right_frame, textvariable=self.lane_var, values=["0", "1", "2", "3"])
        lane_combo.pack(pady=5)

        # Duration
        tk.Label(right_frame, text="Duration (seconds):").pack(pady=5)
        self.duration_var = tk.StringVar(value="10")
        duration_entry = tk.Entry(right_frame, textvariable=self.duration_var)
        duration_entry.pack(pady=5)

        # Send Button
        btn_send = tk.Button(right_frame, text="🚨 SEND OVERRIDE 🚨", 
                             bg="red", fg="white", font=("Arial", 10, "bold"),
                             command=self.send_override)
        btn_send.pack(pady=20, fill=tk.X, padx=10)
        
        # Status Bar
        self.status_var = tk.StringVar(value="Connecting to Cloud...")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def connect_aws(self):
        def _connect():
            try:
                self.aws_client.connect()
                self.status_var.set("Connected to AWS IoT Core")
                self.aws_client.subscribe(TOPIC_LOGS, 1, self.on_message)
                self.aws_client.subscribe(TOPIC_GATEWAY_LOGS, 1, self.on_message)
            except Exception as e:
                self.status_var.set(f"Connection Error: {e}")
        
        threading.Thread(target=_connect, daemon=True).start()

    def on_message(self, client, userdata, msg):
        # Discover devices from logs
        # Topic format: traffic/ID/logs
        try:
            parts = msg.topic.split("/")
            if len(parts) >= 2:
                device_id = parts[1]
                if device_id not in self.devices:
                    self.devices.add(device_id)
                    self.root.after(0, self.update_list)
        except:
            pass

    def update_list(self):
        self.device_list.delete(0, tk.END)
        for d in sorted(list(self.devices)):
            self.device_list.insert(tk.END, d)

    def send_override(self):
        selection = self.device_list.curselection()
        if not selection:
            messagebox.showwarning("No Device", "Please select a target device from the list.")
            return
        
        target_device = self.device_list.get(selection[0])
        lane = int(self.lane_var.get())
        duration = int(self.duration_var.get()) * 1000 # Convert to ms
        
        topic = f"traffic/{target_device}/control"
        payload = json.dumps({
            "lane": lane,
            "duration": duration
        })
        
        self.aws_client.publish(topic, payload, 1)
        status = f"Sent Override: {target_device} Lane {lane} for {duration}ms"
        self.status_var.set(status)
        print(status)

if __name__ == "__main__":
    root = tk.Tk()
    app = TrafficControlApp(root)
    root.mainloop()
