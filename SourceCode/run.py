import os
import time
import sys

def main():
    print(" Booting up Industrial Edge AI Predictive Maintenance System...")
    print("Opening 5 separate Command Prompt windows...")
    print("-" * 60)

    python_exe = sys.executable

    project_dir = os.getcwd()
    mosquitto_path = os.path.join(project_dir, "Mosquitto", "mosquitto.exe")

    print(" Starting 1/5: Start Moqsuitto MQTT Server...")
    os.system(f'start cmd /k "title [1] MQTT SERVER && \"{mosquitto_path}\" -v"')    
    time.sleep(2)  

    print(" Starting 2/5: Industrial Pump Simulator...")    
    os.system('start cmd /k "title [2] PUMP SIMULATOR && python cooling_pump_sim.py"')
    time.sleep(2)  

    print(" Starting 3/5: Edge AI Machine Learning Node...")
    os.system('start cmd /k "title [3] EDGE AI NODE && python Edge_Device.py"')
    time.sleep(3)  

    print(" Starting 4/5: Streamlit Digital Twin Dashboard...")
    os.system('start cmd /k "title [4] STREAMLIT DASHBOARD && streamlit run dashboard.py"')

    print(" Starting 5/5: Control Panel for Fault Simulation...")
    os.system('start cmd /k "title [5] CONTROL PANEL && python control_panel.py"')

    print("-" * 60)
    print(" ALL SYSTEMS ONLINE!")
    print("You can now close this main window. To stop the system later, simply close the 3 new terminal windows.")

if __name__ == "__main__":
    main()