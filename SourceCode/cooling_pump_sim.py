import json
import random
import time
import paho.mqtt.client as mqtt
from paho.mqtt import enums 


BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SENSORS = "bess/cooling_pump_01/sensors"
TOPIC_COMMANDS = "bess/cooling_pump_01/simulation"


HEALTHY = {"vib": 3.0, "temp": 50.0, "curr": 16.0, "cool": 20.0}
CRITICAL = {"vib": 7.1, "temp": 80.0, "curr": 26.0, "cool": 60.0}
RAMP_RATES = {"vib": 0.05, "temp": 0.02, "curr": 0.08, "cool": 0.05}
NOISE = {"vib": 0.05, "temp": 0.05, "curr": 0.1, "cool": 0.05}

current_vals = HEALTHY.copy()
target_vals = HEALTHY.copy()


transient_override = None 


def on_connect(client, userdata, flags, rc):
    print(f" Simulator Connected! Listening for commands...")
    client.subscribe(TOPIC_COMMANDS)

def on_message(client, userdata, msg):
    global target_vals, current_vals, transient_override
    try:
        payload = json.loads(msg.payload.decode())
        command = payload.get("command")
        
        if command == "trigger_fault":
            sensors = list(HEALTHY.keys())
            num_to_fail = random.randint(1, 3)
            failing_sensors = random.sample(sensors, num_to_fail)
            print(f"\n FAULT INJECTED! Gradually degrading: {failing_sensors}\n")
            for s in failing_sensors:
                target_vals[s] = CRITICAL[s]
                
        elif command == "clear_fault":
            print("\n REPAIR ACTIONED: Components cooling down & normalizing...\n")
            target_vals.update(HEALTHY)
            current_vals["vib"] = HEALTHY["vib"]
            current_vals["curr"] = HEALTHY["curr"]
            current_vals["cool"] = HEALTHY["cool"]
            
        elif command == "transient_noise":
            
            transient_override = random.choice(list(HEALTHY.keys()))
            print(f"\n TRANSIENT SPIKE INJECTED into {transient_override} for 1 payload!\n")
            
    except Exception as e:
        print(f" Command Error: {e}")


def generate_and_publish_telemetry(client):
    global current_vals, target_vals, transient_override
    
    while True:
        payload_data = {}
        for key in HEALTHY.keys():
            
            step = (target_vals[key] - current_vals[key]) * RAMP_RATES[key]
            current_vals[key] += step
            
            
            final_val = current_vals[key] + random.normalvariate(0, NOISE[key])
            final_val = max(0.0, min(final_val, CRITICAL[key]))
            
            
            
            
            if key == transient_override:
                final_val = CRITICAL[key]
                
            payload_data[key] = final_val

        
        transient_override = None

        payload = {
            "vibration_rms": round(payload_data["vib"], 3),
            "temperature_c": round(payload_data["temp"], 2),
            "current_a": round(payload_data["curr"], 2),
            "coolant_level_cm": round(payload_data["cool"], 2)
        }

        client.publish(TOPIC_SENSORS, json.dumps(payload))
        print(f"Published: {payload}")
        time.sleep(1) 

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "SensorNode")    
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 120)
    client.loop_start() 
    
    try:
        generate_and_publish_telemetry(client)
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()