#include <WiFi.h>
#include <PubSubClient.h>

/* * SMART ESP32 (EDGE LOGIC)
 * Logic: Internal 7cm Priority.
 * MQTT: Reports status to Local Gateway (PC/Pi).
 */

// --- CONFIG ---
const char* ssid = "";
const char* password = "";
const char* mqtt_server = ""; // <--- CHANGE THIS TO PC IP (Today) / PI IP (Tomorrow)

// --- PINS ---
const int TRIG_PIN = 5;
const int ECHO_PINS[] = {18, 19, 21, 22};
const int RED_PINS[]  = {13, 14, 26, 33};
const int GRN_PINS[]  = {12, 27, 25, 32};
const int MAX_DIST = 7;

// --- GLOBALS ---
String INTERSECTION_ID;
String topic_logs;
String topic_control;
WiFiClient espClient;
PubSubClient client(espClient);

// --- VARIABLES ---
int currentLane = 0;
bool overrideActive = false;
unsigned long overrideEndTime = 0;
int overrideLane = 0;

void setup() {
  Serial.begin(115200);
  
  // Hardware Init
  pinMode(TRIG_PIN, OUTPUT);
  for(int i=0; i<4; i++) {
    pinMode(ECHO_PINS[i], INPUT);
    pinMode(RED_PINS[i], OUTPUT);
    pinMode(GRN_PINS[i], OUTPUT);
  }

  // WiFi & ID
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  
  String mac = WiFi.macAddress();
  mac.replace(":", "");
  INTERSECTION_ID = "INT_" + mac.substring(mac.length() - 4);
  
  topic_logs = "traffic/" + INTERSECTION_ID + "/logs";
  topic_control = "traffic/" + INTERSECTION_ID + "/control";

  // MQTT
  client.setServer(mqtt_server, 1883);
  client.setCallback(mqttCallback);
  
  Serial.println("System Online: " + INTERSECTION_ID);
  allRed();
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Parse Override Command from Gateway
  String msg;
  for(int i=0; i<length; i++) msg += (char)payload[i];
  
  if (msg.indexOf("lane") > -1) {
    int l = msg.substring(msg.indexOf(":")+1, msg.indexOf(",")).toInt();
    long t = msg.substring(msg.lastIndexOf(":")+1, msg.lastIndexOf("}")).toInt();
    
    overrideActive = true;
    overrideLane = l;
    overrideEndTime = millis() + t;
    client.publish(topic_logs.c_str(), "Override Accepted");
  }
}

void reconnect() {
  if (client.connect(INTERSECTION_ID.c_str())) {
    client.publish(topic_logs.c_str(), "ONLINE");
    client.subscribe(topic_control.c_str());
  }
}

float getDistance(int lane) {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PINS[lane], HIGH, 1500); 
  float cm = (duration * 0.0343) / 2;
  if (duration == 0 || cm > MAX_DIST) return 999.0;
  return cm;
}

void allRed() {
  for(int i=0; i<4; i++) {
    digitalWrite(RED_PINS[i], HIGH);
    digitalWrite(GRN_PINS[i], LOW);
  }
}

void setLaneGreen(int lane) {
  allRed();
  digitalWrite(RED_PINS[lane], LOW);
  digitalWrite(GRN_PINS[lane], HIGH);
  String log = "Green: Lane " + String(lane);
  client.publish(topic_logs.c_str(), log.c_str());
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  // OVERRIDE MODE
  if (overrideActive) {
    setLaneGreen(overrideLane);
    if (millis() > overrideEndTime) {
      overrideActive = false;
      allRed();
      delay(500);
    }
    return;
  }

  // NORMAL LOGIC (7cm Priority)
  setLaneGreen(currentLane);
  
  unsigned long start = millis();
  bool switched = false;
  
  while(millis() - start < 5000) {
    if (!client.connected()) reconnect();
    client.loop();
    if (overrideActive) break;

    // Smart Switching
    if (getDistance(currentLane) == 999.0) {
      for(int i=0; i<4; i++) {
        if(i == currentLane) continue;
        if(getDistance(i) <= MAX_DIST) {
          String log = "Priority Switch -> Lane " + String(i);
          client.publish(topic_logs.c_str(), log.c_str());
          currentLane = i;
          switched = true;
          break;
        }
      }
    }
    if(switched) break;
  }
  
  if(!switched && !overrideActive) currentLane = (currentLane + 1) % 4;
  
  allRed();
  delay(500);
}
