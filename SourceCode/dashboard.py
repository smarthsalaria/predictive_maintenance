import json
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from collections import deque
import time

# --- Configuration ---
BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SENSORS = "bess/cooling_pump_01/sensors"
TOPIC_ALERTS = "bess/cooling_pump_01/alerts"

# Keep rolling buffers for ALL four sensor vectors
history_vib = deque(maxlen=50)
history_temp = deque(maxlen=50)
history_curr = deque(maxlen=50)
history_cool = deque(maxlen=50)

def on_connect(client, userdata, flags, rc, properties=None):
    print("[DASHBOARD] Connected to broker. Waiting silently for alerts...")
    client.subscribe(TOPIC_SENSORS)
    client.subscribe(TOPIC_ALERTS)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = json.loads(msg.payload.decode())

    # If it's normal data, save all 4 metrics to their respective histories
    if topic == TOPIC_SENSORS:
        history_vib.append(payload['vibration_rms'])
        history_temp.append(payload['temperature_c'])
        history_curr.append(payload['current_a'])
        history_cool.append(payload['coolant_level_cm'])

    # If it's an alert, trigger the multi-graph!
    elif topic == TOPIC_ALERTS:
        print("\n🚨 [DASHBOARD] CRITICAL ALERT RECEIVED! Generating Comprehensive Incident Report...")
        generate_graph(payload['sensor_data'])

def generate_graph(anomaly_data):
    timestamp = int(time.time())
    
    # Create a 2x2 grid of subplots for a professional diagnostic layout
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Comprehensive Incident Report: Cooling Pump 01\nTimestamp: {timestamp}', fontsize=16, fontweight='bold')

    x_axis = range(len(history_vib))
    fault_index = len(history_vib) - 1 if len(history_vib) > 0 else 0

    # --- Plot 1: Vibration ---
    if len(history_vib) > 0:
        axs[0, 0].plot(x_axis, list(history_vib), color='blue', label='Vibration History')
    axs[0, 0].scatter(fault_index, anomaly_data['vibration_rms'], color='red', s=120, zorder=5, label='Fault Trigger')
    axs[0, 0].axhline(y=7.1, color='orange', linestyle='--', label='ISO Threshold')
    axs[0, 0].set_title('Vibration RMS (mm/s)')
    axs[0, 0].grid(True)
    axs[0, 0].legend()

    # --- Plot 2: Temperature ---
    if len(history_temp) > 0:
        axs[0, 1].plot(x_axis, list(history_temp), color='firebrick', label='Temperature History')
    axs[0, 1].scatter(fault_index, anomaly_data['temperature_c'], color='red', s=120, zorder=5)
    axs[0, 1].axhline(y=75.0, color='orange', linestyle='--', label='NEMA Temp Limit')
    axs[0, 1].set_title('Casing Temperature (°C)')
    axs[0, 1].grid(True)
    axs[0, 1].legend()

    # --- Plot 3: Current ---
    if len(history_curr) > 0:
        axs[1, 0].plot(x_axis, list(history_curr), color='green', label='Current History')
    axs[1, 0].scatter(fault_index, anomaly_data['current_a'], color='red', s=120, zorder=5)
    axs[1, 0].axhline(y=25.0, color='orange', linestyle='--', label='Overcurrent Threshold')
    axs[1, 0].set_title('Motor Current (A)')
    axs[1, 0].grid(True)
    axs[1, 0].legend()

    # --- Plot 4: Coolant Distance ---
    if len(history_cool) > 0:
        axs[1, 1].plot(x_axis, list(history_cool), color='purple', label='Ultrasonic Distance')
    axs[1, 1].scatter(fault_index, anomaly_data['coolant_level_cm'], color='red', s=120, zorder=5)
    axs[1, 1].set_title('Coolant Reservoir Distance (cm) [Increase = Leak]')
    axs[1, 1].grid(True)
    axs[1, 1].legend()

    # Adjust layout so labels don't overlap, then save
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    filename = f'Comprehensive_Report_{timestamp}.png'
    plt.savefig(filename)
    plt.close()
    
    print(f"✅ [DASHBOARD] Comprehensive Report saved successfully as {filename}\n")

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[DASHBOARD] Connection failed: {e}")