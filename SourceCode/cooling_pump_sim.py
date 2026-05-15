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

active_fault_type = None
wear_level = 0.0  # Tracks the progression of the degradation (0.0 to 100.0%)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[SENSOR] Connected to MQTT Broker. Subscribing to simulation instructions...")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    global active_fault_type, wear_level
    try:
        payload = json.loads(msg.payload.decode())
        if "simulation" in payload:
            if payload["simulation"] == "trigger_fault":
                fault_options = ['vibration', 'temperature', 'current', 'coolant']
                active_fault_type = random.choice(fault_options)
                wear_level = 0.0 # Start degradation at 0%
                print(f"\n[SIMULATION] ⚠️ DEGRADATION STARTED! Sensor: [{active_fault_type.upper()}]")
                
            elif payload["simulation"] == "clear_fault":
                active_fault_type = None
                wear_level = 0.0 # Instantly fix the machine
                print("\n[SIMULATION] ✅ REPAIR COMPLETED. Returning to normal baseline.")
    except Exception as e:
        print(f"[SENSOR] Error parsing simulation message: {e}")

def generate_telemetry():
    global active_fault_type, wear_level
    
    vib_base = 3.0
    temp_base = 50.0
    curr_base = 16.5
    ultrasonic_dist_base = 20.0

    while True:
        # 1. Manage Degradation Progression
        if active_fault_type is not None:
            # Increase wear by 2% every second (Takes 50 seconds to hit absolute critical failure)
            wear_level += 2.0 
            wear_level = min(wear_level, 100.0)
        else:
            wear_level = 0.0

        # 2. Generate Base Noise
        vibration = random.normalvariate(vib_base, 0.05)
        temperature = random.normalvariate(temp_base, 0.2)
        current = random.normalvariate(curr_base, 0.1)
        ultrasonic_dist = random.normalvariate(ultrasonic_dist_base, 0.05)

        # 3. Apply Gradual Degradation Math based on Wear Level
        # Formula: Base + (Max_Fault_Spike * (wear_level / 100.0))
        if active_fault_type == 'vibration':
            vibration = random.normalvariate(vib_base + (5.0 * (wear_level/100.0)), 0.1)
        elif active_fault_type == 'temperature':
            temperature = random.normalvariate(temp_base + (40.0 * (wear_level/100.0)), 0.5)
        elif active_fault_type == 'current':
            current = random.normalvariate(curr_base + (15.0 * (wear_level/100.0)), 0.2)
        elif active_fault_type == 'coolant':
            ultrasonic_dist = random.normalvariate(ultrasonic_dist_base + (60.0 * (wear_level/100.0)), 0.1)

        # 4. Package Payload
        payload = {
            "vibration_rms": round(vibration, 3),
            "temperature_c": round(temperature, 2),
            "current_a": round(current, 2),
            "coolant_level_cm": round(ultrasonic_dist, 1)
        }
        
        print(f"[SENSOR OUT] Wear: {wear_level}% | {payload}")
        client.publish(TOPIC_PUB, json.dumps(payload))
        time.sleep(1)

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        print("[SENSOR] Simulator running. Publishing telemetry...")
        generate_telemetry()
    except Exception as e:
        print(f"[SENSOR] Failed to start: {e}")