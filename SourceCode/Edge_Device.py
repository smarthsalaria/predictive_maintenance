import json
import time
import sqlite3
import numpy as np
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest

BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SUB = "bess/cooling_pump_01/sensors"
TOPIC_PUB = "bess/cooling_pump_01/alerts"
DB_FILE = "local_edge_data.db"

# Global variables to hold the normal baseline mathematics
train_mean = None
train_std = None

def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            vibration REAL,
            temperature REAL,
            current REAL,
            coolant_level REAL,
            is_anomaly INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def log_to_db(data, is_anomaly):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry 
            (vibration, temperature, current, coolant_level, is_anomaly)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['vibration_rms'], 
            data['temperature_c'], 
            data['current_a'], 
            data['coolant_level_cm'], 
            int(is_anomaly)
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DATABASE ERROR] Could not save data: {e}")

def get_training_data():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT vibration, temperature, current, coolant_level 
            FROM telemetry 
            WHERE is_anomaly = 0 
            ORDER BY id DESC 
            LIMIT 1000
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        if len(rows) > 50: 
            print(f"[EDGE AI] Successfully loaded {len(rows)} historical records from SQLite.")
            return np.array(rows)
        return None
    except Exception as e:
        print(f"[DATABASE ERROR] Could not read from DB: {e}")
        return None

# --- ML Setup & Baseline Calculation ---
print("[EDGE AI] Initializing Machine Learning Model...")
model = IsolationForest(contamination=0.02, random_state=42)

X_train = get_training_data()

if X_train is not None:
    print("[EDGE AI] Training model using REAL historical database telemetry...")
    model.fit(X_train)
    # Calculate normal baseline for Root Cause Analysis
    train_mean = np.mean(X_train, axis=0)
    train_std = np.std(X_train, axis=0) + 1e-6 # Add tiny amount to prevent divide-by-zero
else:
    print("[EDGE AI] Falling back to synthesized baseline for initial training...")
    X_train_normal = np.random.normal(loc=[3.0, 50.0, 16.5, 20.0], scale=[0.3, 0.8, 0.5, 0.1], size=(500, 4))
    model.fit(X_train_normal)
    train_mean = np.mean(X_train_normal, axis=0)
    train_std = np.std(X_train_normal, axis=0) + 1e-6

print("[EDGE AI] Model trained and ready for live inference.")

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[EDGE AI] Connected to local broker. Listening on {TOPIC_SUB}...")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        data['timestamp'] = time.time()
        
        features = np.array([[
            data['vibration_rms'], 
            data['temperature_c'], 
            data['current_a'], 
            data['coolant_level_cm']
        ]])
        
        prediction = model.predict(features)[0]
        is_anomaly = (prediction == -1)
        
        log_to_db(data, is_anomaly)
        
        if is_anomaly:
            # --- ROOT CAUSE ANALYSIS (Z-Score) ---
            # Calculate how far each sensor deviated from the healthy mean
            z_scores = np.abs((features[0] - train_mean) / train_std)
            
            # Find the index of the highest deviation
            fault_idx = np.argmax(z_scores)
            sensor_names = ['vibration', 'temperature', 'current', 'coolant']
            culprit_sensor = sensor_names[fault_idx]
            
            print(f"🚨 [EDGE AI] Anomaly Detected! RCA identified {culprit_sensor.upper()} as the likely root cause.")
            
            # Inject the AI's conclusion into the data so the dashboard can highlight it
            data['faulty_sensor'] = culprit_sensor
            
            alert_msg = {
                "status": "CRITICAL",
                "message": f"Anomaly isolated to {culprit_sensor}.",
                "sensor_data": data
            }
            client.publish(TOPIC_PUB, json.dumps(alert_msg))
        else:
            print(f"✅ [EDGE AI] Normal State Logged. Listening...", end='\r')
            
    except Exception as e:
        print(f"\n[EDGE AI] Error processing payload: {e}")

if __name__ == "__main__":
    init_database()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[EDGE AI] Connection failed: {e}")