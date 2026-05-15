import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go


st.set_page_config(page_title="Edge PdM Dashboard", layout="wide")
st.title("Industrial Edge Computing: Predictive Maintenance")

DB_FILE = "local_edge_data.db"


CRITICAL_LIMITS = {
    'vibration': 7.1,    
    'temperature': 80.0, 
    'current': 26.0,     
    'coolant': 60.0      
}

COL_MAP = {
    'vibration': 'vibration',
    'temperature': 'temperature',
    'current': 'current',
    'coolant': 'coolant_level'
}

st.markdown("### Live Refresh Control")
pause_refresh = st.toggle(" **FREEZE DASHBOARD** (Turn ON to pause live data so you can drag, pan, and zoom charts)", value=False)

refresh_rate = None if pause_refresh else 2

def fetch_data():
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT timestamp, vibration, temperature, current, coolant_level, is_anomaly, culprit_sensor FROM telemetry ORDER BY id DESC LIMIT 60"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df.iloc[::-1].reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()

def fetch_anomaly_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        query = "SELECT timestamp, culprit_sensor as Root_Cause, vibration, temperature, current, coolant_level as coolant FROM telemetry WHERE is_anomaly = 1 ORDER BY id DESC LIMIT 15"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

def create_sensor_chart(df, col_name, title, limit, active_color):
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['timestamp'], 
        y=df[col_name], 
        mode='lines', 
        name=f"Actual {title}",
        line=dict(color=active_color, width=3)
    ))
    
    fig.add_hline(
        y=limit, 
        line_dash="dot", 
        line_color="red", 
        line_width=2,
        annotation_text=f"CRITICAL LIMIT ({limit})", 
        annotation_position="bottom right",
        annotation_font_color="red"
    )
    
    fig.update_layout(
        margin=dict(l=10, r=20, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="",
        yaxis_title="Sensor Value",
        height=250
    )
    return fig

@st.fragment(run_every=refresh_rate)
def render_live_dashboard():
    df = fetch_data()

    if df.empty or 'culprit_sensor' not in df.columns:
        st.warning("Waiting for Edge AI to populate database... Please ensure Edge_Device.py is running.")
        return

    latest_data = df.iloc[-1]
    
    try:
        is_fault = int(latest_data['is_anomaly']) == 1
    except:
        is_fault = False

    if pd.notnull(latest_data['culprit_sensor']) and latest_data['culprit_sensor'].strip().lower() != "none":
        culprit = str(latest_data['culprit_sensor']).strip().lower()
    else:
        culprit = None

    rul_text = "Analyzing trend over 10-second window..."
    is_critical = False
    
    if is_fault and culprit in COL_MAP:
        sensor_col = COL_MAP[culprit]
        current_val = latest_data[sensor_col]
        limit = CRITICAL_LIMITS[culprit]
        
        if current_val >= limit:
            is_critical = True
        else:
            recent_data = df[sensor_col].tail(10).values
            if len(recent_data) >= 5:
                x_axis = np.arange(len(recent_data))
                slope, _ = np.polyfit(x_axis, recent_data, 1)
                velocity = slope
                
                if velocity > 0.01:
                    remaining_distance = limit - current_val
                    rul_seconds = remaining_distance / velocity
                    rul_text = f"**Degradation Rate:** +{velocity:.2f} per sec | **Remaining Useful Life (RUL):** {rul_seconds:.1f} seconds"
                elif velocity < -0.01:
                    rul_text = "Condition improving. Monitoring..."
                else:
                    rul_text = "Elevated but stable. Monitoring..."

    if is_critical:
        st.error(f"🚨 **CRITICAL SHUTDOWN!** {str(culprit).upper()} breached NEMA/ISO Safety Limits!")
    elif is_fault and culprit:
        st.warning(f"⚠️ **PREDICTIVE MAINTENANCE WARNING:** Early degradation isolated to {str(culprit).upper()}.\n\n{rul_text}")
    else:
        st.success("✅ **System Status:** Normal Operations. All sensors healthy.")

    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vibration (mm/s)", f"{latest_data['vibration']:.2f}")
    col2.metric("Temperature (°C)", f"{latest_data['temperature']:.2f}")
    col3.metric("Current (A)", f"{latest_data['current']:.2f}")
    col4.metric("Coolant Level (cm)", f"{latest_data['coolant_level']:.2f}")

    st.markdown("---")

    st.subheader("Live Edge Telemetry Stream")
    
    chart_col1, chart_col2 = st.columns(2)
    chart_col3, chart_col4 = st.columns(2)

    COLOR_NORMAL = "#00cc66" 
    COLOR_WARNING = "#ffcc00" 
    COLOR_CRITICAL = "#ff0000" 

    if is_critical:
        active_color = COLOR_CRITICAL
        active_tag = " `[CRITICAL LIMIT]`"
    else:
        active_color = COLOR_WARNING
        active_tag = " `[PdM WARNING]`"

    no_menu_config = {'displayModeBar': False}

    with chart_col1:
        st.markdown(f"#### Vibration Trends {active_tag if culprit == 'vibration' else ' `[Normal]`'}")
        fig_vib = create_sensor_chart(df, 'vibration', 'Vibration', CRITICAL_LIMITS['vibration'], active_color if culprit == 'vibration' else COLOR_NORMAL)
        st.plotly_chart(fig_vib, width='stretch', config=no_menu_config)

    with chart_col2:
        st.markdown(f"#### Temperature Profile {active_tag if culprit == 'temperature' else ' `[Normal]`'}")
        fig_temp = create_sensor_chart(df, 'temperature', 'Temperature', CRITICAL_LIMITS['temperature'], active_color if culprit == 'temperature' else COLOR_NORMAL)
        st.plotly_chart(fig_temp, width='stretch', config=no_menu_config)

    with chart_col3:
        st.markdown(f"#### Motor Current {active_tag if culprit == 'current' else ' `[Normal]`'}")
        fig_curr = create_sensor_chart(df, 'current', 'Current', CRITICAL_LIMITS['current'], active_color if culprit == 'current' else COLOR_NORMAL)
        st.plotly_chart(fig_curr, width='stretch', config=no_menu_config)

    with chart_col4:
        st.markdown(f"#### Coolant Level {active_tag if culprit == 'coolant' else ' `[Normal]`'}")
        fig_cool = create_sensor_chart(df, 'coolant_level', 'Coolant', CRITICAL_LIMITS['coolant'], active_color if culprit == 'coolant' else COLOR_NORMAL)
        st.plotly_chart(fig_cool, width='stretch', config=no_menu_config)

    st.markdown("---")

    st.subheader(" Incident History Log")
    history_df = fetch_anomaly_history()
    
    if not history_df.empty:
        history_df['Root_Cause'] = history_df['Root_Cause'].str.upper()
        st.dataframe(history_df, width='stretch', hide_index=True)
    else:
        st.info("No anomalies recorded in the database yet. The system is perfectly healthy.")

render_live_dashboard()