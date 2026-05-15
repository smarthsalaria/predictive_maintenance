import json
import time
import sqlite3
import numpy as np
import paho.mqtt.client as mqtt
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from datetime import datetime

BROKER = "127.0.0.1"
PORT = 1883
TOPIC_SUB = "bess/cooling_pump_01/sensors"
TOPIC_PUB = "bess/cooling_pump_01/alerts"
DB_FILE = "local_edge_data.db"

CRITICAL_LIMITS = {
    'vibration': 7.1,    
    'temperature': 80.0, 
    'current': 26.0,     
    'coolant': 60.0      
}

train_mean = None
train_std = None

consecutive_anomalies = 0  
consecutive_normal = 0
active_fault_state = None 

raw_feature_buffer = []  
degradation_buffer = []  

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
            is_anomaly INTEGER,
            culprit_sensor TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_database()

def log_to_db(data, is_anomaly, culprit_sensor=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetry 
            (vibration, temperature, current, coolant_level, is_anomaly, culprit_sensor)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['vibration_rms'], data['temperature_c'], data['current_a'], data['coolant_level_cm'], int(is_anomaly), culprit_sensor))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def get_training_data():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT vibration, temperature, current, coolant_level FROM telemetry WHERE is_anomaly = 0 ORDER BY id DESC LIMIT 1000')
        rows = cursor.fetchall()
        conn.close()
        
        clean_rows = [r for r in rows if r[0] < 5.0 and r[1] < 60.0 and r[2] < 20.0 and r[3] < 30.0]
        if len(clean_rows) > 50: return np.array(clean_rows)
        return None
    except Exception:
        return None


print("[EDGE AI] Initializing Unsupervised ML Model (Isolation Forest)...")
anomaly_model = IsolationForest(contamination=0.02, random_state=42)
X_train = get_training_data()

if X_train is not None:
    print(f"[EDGE AI] Training ML on CLEAN historical telemetry... ({len(X_train)} records)")
    anomaly_model.fit(X_train)
    train_mean = np.mean(X_train, axis=0)
    train_std = np.maximum(np.std(X_train, axis=0), 0.5) 
else:
    print("[EDGE AI] Falling back to synthesized baseline...")
    X_train_normal = np.random.normal(loc=[3.0, 50.0, 16.5, 20.0], scale=[0.05, 0.2, 0.1, 0.05], size=(500, 4))
    anomaly_model.fit(X_train_normal)
    train_mean = np.mean(X_train_normal, axis=0)
    train_std = np.maximum(np.std(X_train_normal, axis=0), 0.5)

def on_connect(client, userdata, flags, rc, properties=None):
    print(f"[EDGE AI] Connected to local broker. Listening on {TOPIC_SUB}...\n")
    client.subscribe(TOPIC_SUB)

def on_message(client, userdata, msg):
    global consecutive_anomalies, consecutive_normal, active_fault_state, raw_feature_buffer, degradation_buffer
    try:
        data = json.loads(msg.payload.decode())
        data['timestamp'] = datetime.now().strftime("%H:%M:%S")
        
        current_features = [data['vibration_rms'], data['temperature_c'], data['current_a'], data['coolant_level_cm']]
        sensor_names = ['vibration', 'temperature', 'current', 'coolant']
        
        raw_feature_buffer.append(current_features)
        if len(raw_feature_buffer) > 3:
            raw_feature_buffer.pop(0)
        
        smoothed_features = np.mean(raw_feature_buffer, axis=0)
        
       
        ml_anomaly = (anomaly_model.predict([smoothed_features])[0] == -1)
        
        z_scores = np.abs((smoothed_features - train_mean) / train_std)
        stat_anomaly = (np.max(z_scores) > 3.5)
        
        limit_breached = False
        for i, sensor in enumerate(sensor_names):
            if current_features[i] >= CRITICAL_LIMITS[sensor]:
                limit_breached = True
                break
                
        is_anomaly = ml_anomaly or stat_anomaly or limit_breached
        
        if is_anomaly:
            consecutive_normal = 0
            consecutive_anomalies += 1
            
            if consecutive_anomalies >= 3:
                
                fault_idx = np.argmax(z_scores)
                if limit_breached:
                    for i, sensor in enumerate(sensor_names):
                        if current_features[i] >= CRITICAL_LIMITS[sensor]:
                            fault_idx = i
                            break
                            
                culprit_sensor = sensor_names[fault_idx]
                current_value = current_features[fault_idx]
                limit_value = CRITICAL_LIMITS[culprit_sensor]
                
                active_fault_state = culprit_sensor
                data['faulty_sensor'] = culprit_sensor
                log_to_db(data, True, culprit_sensor)
                
                if current_value >= limit_value:
                    print(f"🚨 [SHUTDOWN] {culprit_sensor.upper()} breached NEMA/ISO limit ({current_value:.1f} > {limit_value})!   ")
                    alert_msg = {"status": "CRITICAL", "message": f"LIMIT BREACHED: {culprit_sensor}", "sensor_data": data}
                    client.publish(TOPIC_PUB, json.dumps(alert_msg))
                    degradation_buffer.clear()
                else:
                    degradation_buffer.append(current_value)
                    if len(degradation_buffer) > 10:
                        degradation_buffer.pop(0)
                        
                    rul_text = "Gathering ML context window..."
                    
                    if len(degradation_buffer) >= 5:
                        X = np.arange(len(degradation_buffer)).reshape(-1, 1) 
                        y = np.array(degradation_buffer).reshape(-1, 1)       
                        
                        rul_model = LinearRegression()
                        rul_model.fit(X, y)
                        predicted_velocity = rul_model.coef_[0][0]
                        
                        if predicted_velocity > 0.01:
                            remaining_distance = limit_value - current_value
                            rul_seconds = remaining_distance / predicted_velocity
                            rul_text = f"ML Prediction -> Rate: +{predicted_velocity:.2f}/s | RUL: {rul_seconds:.1f}s"
                        elif predicted_velocity < -0.01:
                            rul_text = "ML Prediction -> Condition improving."
                        else:
                            rul_text = "ML Prediction -> Elevated but stable."

                    print(f"⚠️ [PdM ML WARNING] {culprit_sensor.upper()} | {rul_text}  ")
            else:
                log_to_db(data, True, None)
                print(f"🔎 [EDGE AI] Drift detected. ML verifying ({consecutive_anomalies}/3)...")
                
        else:
            consecutive_anomalies = 0
            if active_fault_state is not None:
                consecutive_normal += 1
                if consecutive_normal >= 3:
                    print(f"\n✅ [EDGE AI] ML CONFIRMS SYSTEM STABLE. Returning to baseline.\n")
                    active_fault_state = None
                    degradation_buffer.clear()
                    log_to_db(data, False, None)
                else:
                    print(f"⏳ [EDGE AI] Repair detected. ML verifying stability ({consecutive_normal}/3)...")
                    data['faulty_sensor'] = active_fault_state
                    log_to_db(data, True, active_fault_state)
            else:
                consecutive_normal = 0
                log_to_db(data, False, None)
                print(f"✅ [EDGE AI] System Health 100%. Baseline normal...                               ", end='\r')
            
    except Exception as e:
        print(f"\n[EDGE AI] Error processing payload: {e}")

if __name__ == "__main__":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_forever()
    except Exception as e:
        print(f"[EDGE AI] Connection failed: {e}")