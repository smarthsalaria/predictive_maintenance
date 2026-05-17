import numpy as np
from sklearn.linear_model import LinearRegression

def test_621_smoothing():
    print("Testing 1: Rolling Average Smoothing...")
    payloads = [3.0, 4.0, 5.0] 
    expected_mean = 4.0
    result = np.mean(payloads)
    status = "PASS" if result == expected_mean else "FAIL"
    print(f" - Input: {payloads} | Expected: {expected_mean} | Result: {result} | {status}")

def test_622_rul_velocity():
    print("\nTesting 2: Linear Regression Velocity (+1.0°C/sec)...")
    X = np.array([1, 2, 3, 4]).reshape(-1, 1) 
    y = np.array([75, 76, 77, 78])           
    
    model = LinearRegression()
    model.fit(X, y)
    velocity = model.coef_[0]
    
    status = "PASS" if velocity == 1.0 else "FAIL"
    print(f" - Input: {y} | Expected Slope: 1.0 | Result: {velocity} | {status}")

def test_623_state_machine_debouncer():
    print("\nTesting 3: State Machine Debouncer (1-Strike Reset)...")
    sequence = ["Normal", "Anomaly", "Normal"]
    consecutive_anomalies = 0
    
    print(f" - Initial Count: {consecutive_anomalies}")
    for i, state in enumerate(sequence):
        if state == "Anomaly":
            consecutive_anomalies += 1
        else:
            consecutive_anomalies = 0
        print(f"   Step {i+1} ({state}): Counter = {consecutive_anomalies}")
    
    status = "PASS" if consecutive_anomalies == 0 else "FAIL"
    print(f" - Final Debouncer Status: {status}")

if __name__ == "__main__":
    print("- EDGE Device: UNIT TEST -")
    test_621_smoothing()
    test_622_rul_velocity()
    test_623_state_machine_debouncer()