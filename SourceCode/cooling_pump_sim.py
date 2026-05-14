import time
import json
import random
import threading
import paho.mqtt.client as mqtt

# --- Configuration ---
BROKER = "127.0.0.1"
PORT = 1883
TOPIC_PUB = "bess/cooling_pump_01/sensors"
TOPIC_SUB = "bess/cooling_pump_01/simulation"

# Global state to track WHICH sensor is failing (None if system is healthy)
active_fault_type = None

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[SENSOR] Connected to MQTT Broker. Subscribing to simulation instructions...")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    global active_fault_type
    try:
        payload = json.loads(msg.payload.decode())
        if "simulation" in payload:
            if payload["simulation"] == "trigger_fault":
                # Randomly select ONE sensor to fail
                fault_options = ['vibration', 'temperature', 'current', 'coolant']
                active_fault_type = random.choice(fault_options)
                print(f"\n[SIMULATION RECVD] ⚠️ FAULT ACTIVATED! Faltering Sensor: [{active_fault_type.upper()}]")
                
            elif payload["simulation"] == "clear_fault":
                active_fault_type = None
                print("\n[SIMULATION RECVD] ✅ FAULT CONDITION CLEARED. Returning to normal.")
    except Exception as e:
        print(f"[SENSOR] Error parsing simulation message: {e}")

def generate_telemetry():
    global active_fault_type
    
    vib_base = 3.0
    temp_base = 50.0
    curr_base = 16.5
    ultrasonic_dist_base = 20.0

    while True:
        # Generate normal noise
        vibration = random.normalvariate(vib_base, 0.3)
        temperature = random.normalvariate(temp_base, 0.8)
        current = random.normalvariate(curr_base, 0.5)
        
        if active_fault_type != 'coolant':
            if ultrasonic_dist_base > 20.0:
                ultrasonic_dist_base -= 2.0 
            ultrasonic_dist_base = max(20.0, ultrasonic_dist_base)

        # Apply specific fault
        if active_fault_type == 'vibration':
            vibration = random.normalvariate(vib_base + 6.5, 1.2)
        elif active_fault_type == 'temperature':
            temperature = random.normalvariate(temp_base + 35.0, 2.0)
        elif active_fault_type == 'current':
            current = random.normalvariate(curr_base + 15.0, 3.0)
        elif active_fault_type == 'coolant':
            ultrasonic_dist_base += 1.5
            if ultrasonic_dist_base > 80.0: 
                ultrasonic_dist_base = 80.0
                
        ultrasonic_dist = random.normalvariate(ultrasonic_dist_base, 0.1)

        # STRICTLY RAW DATA. No cheat labels.
        payload = {
            "vibration_rms": round(vibration, 3),
            "temperature_c": round(temperature, 2),
            "current_a": round(current, 2),
            "coolant_level_cm": round(ultrasonic_dist, 1)
        }
        
        print(f"[SENSOR OUT] {payload}")
        client.publish(TOPIC_PUB, json.dumps(payload))
        time.sleep(1)
if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start() # Start network loop in background
        print("[SENSOR] Simulator running. Publishing telemetry...")
        generate_telemetry() # Run data generation in foreground
    except Exception as e:
        print(f"[SENSOR] Failed to start: {e}")