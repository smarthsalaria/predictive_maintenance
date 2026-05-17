import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go


st.set_page_config(
    page_title="Industrial Edge Dashboard", 
    page_icon="", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        h1, h2, h3 { color: #f8fafc; }
        .stMetric label { color: #94a3b8 !important; }
        .stMetric value { color: #deff9a !important; }
        div[data-testid="stDataFrame"] { background-color: #0f172a; }
    </style>
""", unsafe_allow_html=True)

DB_FILE = "local_edge_data.db"
LIMITS = {"vibration": 7.1, "temperature": 80.0, "current": 26.0, "coolant": 60.0}

def fetch_telemetry(limit=60):
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        df = pd.read_sql(f"SELECT * FROM telemetry ORDER BY id DESC LIMIT {limit}", conn)
        conn.close()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df.iloc[::-1].reset_index(drop=True) 
    except Exception:
        return pd.DataFrame()

def fetch_incident_history():
    try:
        conn = sqlite3.connect(DB_FILE, timeout=5)
        df = pd.read_sql("SELECT timestamp, culprit_sensor AS Root_Cause, vibration, temperature, current, coolant_level AS coolant FROM telemetry WHERE is_anomaly = 1 ORDER BY id DESC LIMIT 15", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

st.markdown("""
    <style>
        /* Force the logo height and ensure it doesn't stretch */
        [data-testid="stImage"] img {
            height: auto !important;  /* Adjust this to make the logo taller or shorter */
            width: auto !important;
            margin-left: auto;
            margin-right: auto;
            display: block;
        }
        /* Tighten the gap between the title and the logo */
        .header-container {
            margin-top: -20px;
            text-align: center;
        }
    </style>
""", unsafe_allow_html=True)

header_content, header_control = st.columns([0.9, 0.1])

with header_content:
    _, logo_center, _ = st.columns([0.4, 0.2, 0.4])
    with logo_center:
        try:
            
            st.image("cu_logo.png") 
        except Exception:
            st.markdown("<h1 style='text-align: center;'>🎓</h1>", unsafe_allow_html=True)

    st.markdown("""
        <div style="text-align: center;">
            <h1 style="margin-bottom: 0px;">Industrial Equipment Failure Prediction Using Edge Analytics</h1>
            <p style="font-size: 18px; color: #94a3b8; margin-top: 5px;">
                Real-time predictive maintenance monitoring for Industrial Asset.<br>
                <strong>Current Asset:</strong> Heavy-Duty Liquid Cooling Pump Motor.
            </p>
        </div>
    """, unsafe_allow_html=True)


with header_control:
    # Keeps the pause button at the top right so it doesn't interrupt the center flow
    st.markdown("<br>", unsafe_allow_html=True)
    is_paused = st.toggle("⏸️ Pause", key="pause_feed", value=False)


@st.fragment(run_every="1s")
def render_live_dashboard():
    
    if not st.session_state.pause_feed:
        df = fetch_telemetry(60)
        st.session_state['cached_df'] = df
    else:
        df = st.session_state.get('cached_df', pd.DataFrame())
    
    if df.empty:
        st.warning(" No telemetry data found. Is the Edge AI node running?")
        return

    latest = df.iloc[-1]
    is_anomaly = latest['is_anomaly'] == 1
    culprit_string = str(latest['culprit_sensor']).upper()
    velocity = float(latest['velocity']) if 'velocity' in latest else 0.0
    confidence = float(latest['confidence']) if 'confidence' in latest else 0.0
    
    
    confidence_text = f" |  AI Confidence: {confidence}%"
    rul_text = " | RUL: Optimal/Fault"

    if culprit_string != "NONE" and velocity > 0:
        min_countdown = float('inf')
        for sensor_name in ["vibration", "temperature", "current", "coolant"]:
            if sensor_name.upper() in culprit_string:
                db_col = sensor_name if sensor_name != "coolant" else "coolant_level"
                current_val = latest[db_col]
                limit_val = LIMITS[sensor_name]
                
                if current_val < limit_val:
                    time_left = (limit_val - current_val) / velocity
                    if time_left < min_countdown:
                        min_countdown = time_left
        
        if min_countdown != float('inf'):
            rul_text = f" |  Remaining Useful Life: {min_countdown:.1f}s"
            
    
    banner_extras = confidence_text + rul_text
            
    
    if is_anomaly:
        st.error(f" CRITICAL ASSET FAULT: Motor Seizure / Leak Imminent ({culprit_string}){banner_extras}")
    elif culprit_string != "NONE":
        st.warning(f" PdM WARNING: Mechanical drift detected in pump motor ({culprit_string}).{banner_extras}")
    else:
        st.success(f" SYSTEM NORMAL: Asset operating within healthy mechanical baselines.{banner_extras}")

    
    cols = st.columns(4)
    cols[0].metric("Vibration RMS", f"{latest['vibration']:.3f} mm/s")
    cols[1].metric("Casing Temp", f"{latest['temperature']:.2f} °C")
    cols[2].metric("Motor Current", f"{latest['current']:.2f} A")
    cols[3].metric("Coolant Level", f"{latest['coolant_level']:.2f} cm")
    
    st.markdown("---")

    
    chart_cols = st.columns(2)
    sensors = ["vibration", "temperature", "current", "coolant"]
    db_cols = ["vibration", "temperature", "current", "coolant_level"]
    titles = ["Vibration Trends", "Temperature Profile", "Motor Current", "Coolant Tank Ultrasonic Distance"]
    
    for idx, (sensor_name, db_col, title) in enumerate(zip(sensors, db_cols, titles)):
        latest_val = latest[db_col]
        limit_val = LIMITS[sensor_name]
        is_culprit = sensor_name.upper() in culprit_string
        
        if is_culprit and is_anomaly:
            status_text = "**:red[[CRITICAL AI FAULT]]**"
            line_color = "#ef4444" 
        elif is_culprit and not is_anomaly:
            status_text = "**:orange[[PdM WARNING]]**"
            line_color = "#f59e0b" 
        else:
            status_text = "**:green[[Normal]]**"
            line_color = "#10b981" 
            
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df[db_col], mode='lines', 
            line=dict(color=line_color, width=3),
            fill='tozeroy',
            fillcolor=f"rgba{tuple(int(line_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.1,)}"
        ))
        
        fig.add_hline(
            y=limit_val, line_dash="dash", line_color="#ef4444", 
            annotation_text=f"SHUTDOWN LIMIT ({limit_val})", 
            annotation_position="bottom right",
            annotation_font_color="#ef4444"
        )
        
        if is_culprit and velocity > 0 and latest_val < limit_val:
            last_time = df['timestamp'].iloc[-1]
            time_to_limit = (limit_val - latest_val) / velocity
            time_to_limit = min(time_to_limit, 45) 
            future_time = last_time + pd.Timedelta(seconds=time_to_limit)
            future_val = latest_val + (velocity * time_to_limit)
            
            fig.add_trace(go.Scatter(
                x=[last_time, future_time], y=[latest_val, future_val], 
                mode='lines', line=dict(color='yellow', width=3, dash='dot'), name="RUL Projection"
            ))
                      
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10), height=220,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#64748b")),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#64748b")),
            showlegend=False
        )
        
        with chart_cols[idx % 2]:
            st.markdown(f"### {title} {status_text}")
            st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

    st.markdown("---")
    st.markdown("###  Incident History Log")
    incidents_df = fetch_incident_history()
    
    if not incidents_df.empty:
        st.dataframe(incidents_df, width='stretch', hide_index=True, height=250)
    else:
        st.info("No anomalies recorded. The asset is operating optimally.")

render_live_dashboard()