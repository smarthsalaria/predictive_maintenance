import json
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC = "bess/cooling_pump_01/simulation"

def send_command(cmd_string):
    client = mqtt.Client()
    try:
        client.connect(BROKER, PORT, 60)
        
        payload = json.dumps({"simulation": cmd_string}) 
        
        client.publish(TOPIC, payload)
        print(f"\n[CONTROL PANEL] Successfully sent: {payload}")
        
        client.disconnect()
    except Exception as e:
        print(f"[CONTROL PANEL] Error: {e}")

if __name__ == "__main__":
    print("\n=== EDGE PdM CONTROL PANEL ===")
    while True:
        choice = input("\nSelect an option:\n(1) Trigger Fault\n(2) Clear Fault\n(3) Exit\nChoice: ")
        
        if choice == '1':
            send_command("trigger_fault")
        elif choice == '2':
            send_command("clear_fault")
        elif choice == '3':
            print("Exiting...")
            break
        else:
            print("Invalid choice. Press 1, 2, or 3.")