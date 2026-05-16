import json
import time
import sqlite3
import numpy as np
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from collections import deque


BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SENSORS = "bess/cooling_pump_01/sensors"
TOPIC_ALERTS = "bess/cooling_pump_01/alerts"
DB_FILE = "local_edge_data.db"
LIMITS = {"vibration": 7.1, "temperature": 80.0, "current": 26.0, "coolant": 60.0}


consecutive_anomalies = 0
total_incidents = 0  
STRIKE_THRESHOLD = 3
anomaly_model = None
train_mean = None
train_std = None

rul_window_y = deque(maxlen=10)
rul_window_x = deque(maxlen=10)
reading_counter = 0


def init_db():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                vibration REAL NOT NULL,
                temperature REAL NOT NULL,
                current REAL NOT NULL,
                coolant_level REAL NOT NULL,
                is_anomaly INTEGER NOT NULL,
                culprit_sensor TEXT,
                velocity REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.0
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry(timestamp)')
        conn.commit()
        conn.close()
        print("✅ SQLite Database Initialized.")
    except Exception as e:
        print(f"❌ Database Init Error: {e}")


def train_model():
    global anomaly_model, train_mean, train_std
    print("🧠 Fetching historical baseline from SQLite...")
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT vibration, temperature, current, coolant_level FROM telemetry WHERE is_anomaly = 0 ORDER BY id DESC LIMIT 1000")
        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 50:
            print("⚠️ Insufficient historical data. Synthesizing initial baseline...")
            X_train = np.array([
                [np.random.normal(3.0, 0.05), np.random.normal(50.0, 0.5), np.random.normal(16.0, 0.1), np.random.normal(20.0, 0.05)]
                for _ in range(500)
            ])
        else:
            X_train = np.array(rows)
            print(f"✅ Successfully loaded {len(X_train)} historical records.")

        anomaly_model = IsolationForest(contamination=0.05, random_state=42)
        anomaly_model.fit(X_train)
        train_mean = np.mean(X_train, axis=0)
        train_std = np.std(X_train, axis=0)
        print("✅ Isolation Forest Model Trained.")
    except Exception as e:
        print(f"❌ Model Training Error: {e}")


def on_message(client, userdata, msg):
    global consecutive_anomalies, total_incidents, anomaly_model, train_mean, train_std
    global rul_window_x, rul_window_y, reading_counter

    start_time = time.perf_counter()
    reading_counter += 1

    try:
        data = json.loads(msg.payload.decode())
        vib = data['vibration_rms']
        temp = data['temperature_c']
        curr = data['current_a']
        cool = data['coolant_level_cm']
        features = np.array([[vib, temp, curr, cool]])

        ml_anomaly = (anomaly_model.predict(features)[0] == -1)
        safe_std_devs = np.maximum(train_std, 0.5) 
        z_scores = np.abs((features[0] - train_mean) / safe_std_devs)
        stat_anomaly = (np.max(z_scores) > 4.0)

        failing_sensors = []
        sensor_names = ["vibration", "temperature", "current", "coolant"]
        sensor_values = [vib, temp, curr, cool]
        primary_culprit_idx = -1
        max_z = -1

        if stat_anomaly or ml_anomaly:
            for i in range(4):
                if z_scores[i] > 4.0:
                    if sensor_names[i] == "current" and curr < 20.0: continue
                    elif sensor_names[i] == "temperature" and temp < 60.0: continue
                    elif sensor_names[i] == "vibration" and vib < 5.0: continue
                    elif sensor_names[i] == "coolant" and cool < 35.0: continue
                    
                    failing_sensors.append(sensor_names[i].upper())
                    if z_scores[i] > max_z:
                        max_z = z_scores[i]
                        primary_culprit_idx = i

        if len(failing_sensors) > 0:
            is_anomaly = True
            culprit_sensor = ", ".join(failing_sensors)
        else:
            is_anomaly = False
            culprit_sensor = "None"

        
        if is_anomaly:
            consecutive_anomalies += 1
            total_incidents += 1  
            if primary_culprit_idx != -1:
                rul_window_y.append(sensor_values[primary_culprit_idx])
                rul_window_x.append(reading_counter)
        else:
            if consecutive_anomalies > 0:
                consecutive_anomalies -= 1 

        
        
        historical_weight = min(20.0, total_incidents * 0.5) 
        
        active_weight = min(55.0, (consecutive_anomalies / STRIKE_THRESHOLD) * 55.0)
        
        intensity_weight = 0.0
        if max_z > 4.0 and is_anomaly:
            intensity_weight = min(25.0, (max_z - 4.0) * 5.0)
            
        confidence_score = round(historical_weight + active_weight + intensity_weight, 1)

        
        degradation_velocity = 0.0
        if consecutive_anomalies >= STRIKE_THRESHOLD and len(rul_window_y) >= 3:
            X = np.array(rul_window_x).reshape(-1, 1)
            y = np.array(rul_window_y)
            rul_model = LinearRegression()
            rul_model.fit(X, y)
            degradation_velocity = rul_model.coef_[0]

        
        is_near_critical = False
        if len(failing_sensors) > 0:
            for i, name in enumerate(sensor_names):
                if name.upper() in culprit_sensor:
                    if sensor_values[i] >= (LIMITS[name] * 0.95):
                        is_near_critical = True
                        break

        
        if consecutive_anomalies >= STRIKE_THRESHOLD and is_near_critical:
            system_status = "CRITICAL"
            anomaly_flag = 1  
            status_icon = "🔴"
        elif consecutive_anomalies >= STRIKE_THRESHOLD:
            system_status = "PdM WARNING (Tracking RUL)"
            anomaly_flag = 0  
            status_icon = "🟠"
        elif consecutive_anomalies > 0:
            system_status = "PdM WARNING (Verifying)"
            anomaly_flag = 0
            status_icon = "🟡"
        else:
            system_status = "NORMAL"
            anomaly_flag = 0
            status_icon = "🟢"

        
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5)
            cursor = conn.cursor()
            db_culprit = culprit_sensor if consecutive_anomalies > 0 else "None"
            
            cursor.execute(
                "INSERT INTO telemetry (vibration, temperature, current, coolant_level, is_anomaly, culprit_sensor, velocity, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vib, temp, curr, cool, anomaly_flag, db_culprit, degradation_velocity, confidence_score)
            )
            conn.commit()
            conn.close()
        except sqlite3.OperationalError:
            pass 

        if system_status != "NORMAL":
            alert_payload = {"status": system_status, "root_cause": culprit_sensor, "velocity": round(degradation_velocity, 4), "confidence": confidence_score}
            client.publish(TOPIC_ALERTS, json.dumps(alert_payload))

        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        print(f"{status_icon} Inference: {latency_ms:.2f}ms | Conf: {confidence_score}% | Strikes: {consecutive_anomalies} | History: {total_incidents}")

    except Exception as e:
        print(f"❌ Processing Error: {e}")

def on_connect(client, userdata, flags, rc):
    print(f"✅ Connected to MQTT Broker with code {rc}")
    client.subscribe(TOPIC_SENSORS)

def start_edge_node():
    init_db()
    train_model()
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    start_edge_node()