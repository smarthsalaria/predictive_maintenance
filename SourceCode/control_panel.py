import json
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
TOPIC_COMMANDS = "bess/cooling_pump_01/simulation"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

def send_command(cmd_string):
    payload = {"command": cmd_string}
    client.publish(TOPIC_COMMANDS, json.dumps(payload))
    print(f"--> Sent: {cmd_string}")

if __name__ == "__main__":
    print("--- FAULT TEST CONTROL PANEL ---")
    print("1. Inject Random Fault in the Industrial Asset")
    print("2. Inject 1-Second Random Transient Spike")
    print("3. Clear Fault / Execute Repair")
    print("0. Exit")
    
    while True:
        choice = input("\nEnter command number: ")
        if choice == "1":
            send_command("trigger_fault")
        elif choice == "2":
            send_command("transient_noise")
        elif choice == "3":
            send_command("clear_fault")
        elif choice == "0":
            break
        else:
            print("Invalid choice.")