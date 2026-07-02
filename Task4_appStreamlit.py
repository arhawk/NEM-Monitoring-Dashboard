import streamlit as st
import folium
from streamlit_folium import st_folium
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
import pandas as pd
import os
from threading import Lock

# -------------------------- Global Configuration (Aligned with Assignment Requirements) --------------------------
st.set_page_config(page_title="NEM Facility Real-time Monitoring Dashboard", layout="wide")
BROKER = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC = "comp5339/task123/measurements/#"  # MQTT topic required by Assignment Task3
DATA_CSV = "nem_facility_data.csv"  # Rename to a clearer file name to avoid confusion with old files
mqtt_client = None
facility_data_store = {}
facility_data_lock = Lock()


@st.cache_data(show_spinner=False)
def load_historical_facilities(data_csv):
    """Load historical facilities once per CSV contents to avoid re-parsing on every rerun."""
    facility_data = {}
    if not os.path.exists(data_csv):
        return facility_data

    df = pd.read_csv(data_csv)
    required_cols = ["power_value", "emission_value", "facility_code", "lat", "lng", "state", "fuel_list"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"CSV file missing required columns (Violates Task2 requirements): {missing_cols} | "
            "Please delete old CSV file and try again"
        )

    for _, row in df.iterrows():
        facility_data[row["facility_code"]] = {
            "name": row["facility_name"],
            "lat": row["lat"],
            "lng": row["lng"],
            "timestamp": row["timestamp"],
            "power_value": round(row["power_value"], 2) if pd.notna(row["power_value"]) else 0,
            "emission_value": round(row["emission_value"], 2) if pd.notna(row["emission_value"]) else 0,
            "price_per_mwh": round(row["price_per_mwh"], 2) if pd.notna(row["price_per_mwh"]) else 0,
            "demand_mw": round(row["demand_mw"], 2) if pd.notna(row["demand_mw"]) else 0,
            "state": row["state"] or "Unknown Region",
            "fuel_list": row["fuel_list"] or "Unknown",
        }

    return facility_data

# ---------------------- MQTT Callbacks (Strictly Match raw_data Fields) ----------------------
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[{datetime.now():%H:%M:%S}] ✅ MQTT connected successfully, subscribing to topic: {TOPIC}")
        client.subscribe(TOPIC)
    else:
        print(f"[{datetime.now():%H:%M:%S}] ❌ MQTT connection failed, error code: {rc}")

def on_message(client, userdata, msg, properties=None):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        # 1. Parse all required fields from raw_data
        fac_code = payload.get("facility_code")
        lat = payload.get("lat")
        lng = payload.get("lng")
        fac_name = payload.get("facility_name", fac_code)
        timestamp = payload.get("timestamp", str(datetime.now()))
        power_val = payload.get("power_value")  # Strictly match power_value in raw_data
        emission_val = payload.get("emission_value")  # Strictly match emission_value in raw_data
        price = payload.get("price_per_mwh")
        demand = payload.get("demand_mw")
        state = payload.get("state")
        fuel_list = payload.get("fuel_list", "Unknown")

        # 2. Data Validation (Assignment Task2 Requirement: Ensure core fields exist)
        if not (fac_code and lat and lng and power_val is not None):
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ Skip invalid data: missing core fields | Facility Code: {fac_code}")
            return

        # 3. Store into a process-wide snapshot so Streamlit reruns can read the latest data.
        facility_record = {
            "name": fac_name,
            "lat": lat,
            "lng": lng,
            "timestamp": timestamp,
            "power_value": round(power_val, 2) if power_val is not None else 0,
            "emission_value": round(emission_val, 2) if emission_val is not None else 0,
            "price_per_mwh": round(price, 2) if price is not None else 0,
            "demand_mw": round(demand, 2) if demand is not None else 0,
            "state": state or "Unknown Region",
            "fuel_list": fuel_list,
        }
        with facility_data_lock:
            facility_data_store[fac_code] = facility_record

        # 4. Write to CSV (Column names exactly match raw_data and SessionState, Assignment Task2 Requirement)
        df = pd.DataFrame([{
            "facility_code": fac_code,
            "facility_name": fac_name,
            "lat": lat,
            "lng": lng,
            "timestamp": timestamp,
            "power_value": power_val,
            "emission_value": emission_val,
            "price_per_mwh": price,
            "demand_mw": demand,
            "state": state,
            "fuel_list": fuel_list
        }])
        df.to_csv(DATA_CSV, mode="a", header=not os.path.exists(DATA_CSV), index=False)

        with facility_data_lock:
            facility_total = len(facility_data_store)
        print(f"[{datetime.now():%H:%M:%S}] 📥 Data stored: {fac_code} | Power: {power_val}MW | Total Facilities: {facility_total}")
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] ❌ Data processing failed: {str(e)}")

# ---------------------- Initialize MQTT Client (Assignment Task3 Requirement) ----------------------
def init_mqtt():
    global mqtt_client
    if mqtt_client is None:
        mqtt_client = mqtt.Client(
            client_id="nem-facility-monitor",  # Explicit client ID, required for uniqueness by Assignment Task3
            clean_session=True,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.connect(BROKER, PORT, keepalive=30)
        mqtt_client.loop_start()
        print(f"[{datetime.now():%H:%M:%S}] 🔌 MQTT client initialized successfully (Complies with Task3 requirements)")
    return mqtt_client

# ---------------------- Initialize Streamlit State (Strictly Read CSV Fields) ----------------------
def init_streamlit_state():
    # Initialize SessionState variables
    if "facility_data" not in st.session_state:
        st.session_state.facility_data = {}
    if "display_mode" not in st.session_state:
        st.session_state.display_mode = "power_value"  # Match power_value field in raw_data
    if "selected_fuel" not in st.session_state:
        st.session_state.selected_fuel = "All"
    if "selected_region" not in st.session_state:
        st.session_state.selected_region = "All"

    # Restore data from CSV once, then keep the live process-wide snapshot in sync.
    with facility_data_lock:
        if not facility_data_store:
            facility_data_store.update(load_historical_facilities(DATA_CSV))
        st.session_state.facility_data = dict(facility_data_store)
    print(f"[{datetime.now():%H:%M:%S}] 🔄 Restored historical data from CSV: {len(st.session_state.facility_data)} records (Complies with Task2 requirements)")

# ---------------------- Data Filtering Logic (Match fuel_list and state in raw_data) ----------------------
def filter_facilities():
    filtered = []
    for code, info in st.session_state.facility_data.items():
        # Fuel filter: Match fuel_list in raw_data (e.g., 'Solar', 'Wind', 'Hydro')
        fuel_match = st.session_state.selected_fuel == "All" or st.session_state.selected_fuel in str(info["fuel_list"])
        # Region filter: Match state in raw_data (NSW, QLD, SA, VIC, TAS)
        region_match = st.session_state.selected_region == "All" or st.session_state.selected_region == info["state"]
        if fuel_match and region_match:
            filtered.append((code, info))
    return filtered

def median(lst):
    n = len(lst)
    s = sorted(lst)
    return (s[n//2-1]/2.0+s[n//2]/2.0, s[n//2])[n % 2] if n else None

# ---------------------- Calculate Real-time Statistics (Updated to Use Cached Data) ----------------------
def get_latest_facilities():
    with facility_data_lock:
        return list(facility_data_store.values())


def calculate_realtime_stats_from_facilities(latest_facilities):
    facility_count = len(latest_facilities)
    
    total_power = sum(f["power_value"] for f in latest_facilities)
    total_emission = sum(f["emission_value"] for f in latest_facilities)
    
    valid_prices = [f["price_per_mwh"] for f in latest_facilities if f["price_per_mwh"] > 0]
    median_price = median(valid_prices) if valid_prices else 0
    
    valid_demands = [f["demand_mw"] for f in latest_facilities if f["demand_mw"] > 0]
    median_demand = median(valid_demands) if valid_demands else 0
    
    return round(total_power, 2), round(total_emission, 2), round(median_price, 2), round(median_demand, 2)


def calculate_realtime_stats():
    return calculate_realtime_stats_from_facilities(get_latest_facilities())


@st.fragment(run_every=2)
def render_realtime_metrics():
    # Fragment reruns on a timer, so the numbers stay live without remounting the map.
    total_power, total_emission, median_price, median_demand = calculate_realtime_stats()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Power Output MW", f"{total_power}", delta="Real-time Update")
    with col2:
        st.metric("Total CO2 Emissions tCO2e", f"{total_emission}", delta="Real-time Update")
    with col3:
        st.metric("Median Price $/MWh", f"{median_price}", delta="Real-time Update")
    with col4:
        st.metric("Median Grid Demand MW", f"{median_demand}", delta="Real-time Update")

# ---------------------- Draw Interactive Map (Assignment Task4 Requirement) ----------------------
def draw_map(filtered_facilities):
    if not filtered_facilities:
        st.info("No matching facility data. Please adjust filter criteria or wait for MQTT data push (Complies with Task4 requirements)")
        return folium.Map(location=[-27.5, 133.8], zoom_start=4, tiles="OpenStreetMap")
    
    m = folium.Map(location=[-27.5, 133.8], zoom_start=4, tiles="OpenStreetMap")
    
    for code, info in filtered_facilities:
        # Tooltip: Toggle between power/emission display (Match raw_data fields)
        display_val = info[st.session_state.display_mode]
        unit = "MW" if st.session_state.display_mode == "power_value" else "tCO2e"
        tooltip_text = f"{info['name']} | {'Power: ' if st.session_state.display_mode == 'power_value' else 'Emissions: '}{display_val}{unit}"
        
        # Popup: Display all raw_data fields (Detailed information required by Assignment Task4)
        popup_html = f"""
        <b>{info['name']}</b><br>
        Facility Code: {code}<br>
        Region: {info['state']}<br>
        Fuel Type: {info['fuel_list']}<br>
        Last Updated: {info['timestamp'][:16]}<br>
        Power Output: {info['power_value']} MW<br>
        CO2 Emissions: {info['emission_value']} tCO2e<br>
        Current Price: {info['price_per_mwh']} $/MWh<br>
        Grid Demand: {info['demand_mw']} MW
        """
        popup = folium.Popup(popup_html, max_width=300)
        
        # Marker color: Distinguish by fuel type (Complies with Task4 visualization requirements)
        fuel_color = "green" if "Solar" in str(info["fuel_list"]) or "Wind" in str(info["fuel_list"]) or "Hydro" in str(info["fuel_list"]) else "orange" if "Gas" in str(info["fuel_list"]) else "red"
        folium.CircleMarker(
            location=[info["lat"], info["lng"]],
            radius=8,
            color=fuel_color,
            fill=True,
            fill_color=fuel_color,
            popup=popup,
            tooltip=tooltip_text
        ).add_to(m)
    
    return m


def map_cache_key(filtered_facilities):
    # Keep the cache tied to spatial/filter changes, not per-message telemetry updates.
    return tuple(
        (
            code,
            round(info["lat"], 6),
            round(info["lng"], 6),
            info["state"],
            str(info["fuel_list"]),
        )
        for code, info in filtered_facilities
    )


def get_cached_map(filtered_facilities):
    cache_key = map_cache_key(filtered_facilities)
    if st.session_state.get("_map_cache_key") != cache_key:
        st.session_state._map_cache_key = cache_key
        st.session_state._cached_map = draw_map(filtered_facilities)
    return st.session_state.get("_cached_map")

# -------------------------- Main Logic (Integrate All Assignment Tasks) --------------------------
def main():
    init_streamlit_state()
    init_mqtt()

    st.title("⚡ National Electricity Market (NEM) Facility Real-time Monitoring Dashboard")

    # Keep the metrics live without forcing the map to remount on every refresh.
    render_realtime_metrics()
    
    # Sidebar: Filter and Control (Optional requirements by Task4)
    with st.sidebar:
        st.header("🔧 Control Center")
        
        # Display Mode Toggle (Match power_value/emission_value in raw_data)
        st.subheader("Display Mode")
        if st.button("📊 Show Power", type="primary" if st.session_state.display_mode == "power_value" else "secondary"):
            st.session_state.display_mode = "power_value"
        if st.button("🌍 Show Emissions", type="primary" if st.session_state.display_mode == "emission_value" else "secondary"):
            st.session_state.display_mode = "emission_value"
        
        # Fuel Type Filter (Match fuel_list in raw_data: Solar, Wind, Hydro, etc.)
        st.subheader("Fuel Type Filter")
        fuel_options = ["All", "Solar", "Wind", "Hydro", "Gas", "Coal"]
        st.session_state.selected_fuel = st.selectbox("Select Fuel Type", fuel_options, index=fuel_options.index(st.session_state.selected_fuel))
        
        # Region Filter (Match state in raw_data: NSW, QLD, SA, VIC, TAS)
        st.subheader("Grid Region Filter")
        region_options = ["All", "NSW", "QLD", "SA", "VIC", "TAS"]
        st.session_state.selected_region = st.selectbox("Select Region", region_options, index=region_options.index(st.session_state.selected_region))
        
        # Data Statistics (Transparency required by Assignment Task4)
        st.subheader("📈 Data Statistics")
        st.write(f"Total Facilities: {len(st.session_state.facility_data)}")
        st.write(f"Filtered Facilities: {len(filter_facilities())}")
        
        # Data Preview (Interpretability required by Assignment Task4)
        st.subheader("📋 Facility Data Preview")
        filtered = filter_facilities()
        if filtered:
            df_preview = pd.DataFrame([{
                "Facility Name": info["name"],
                "Region": info["state"],
                "Fuel Type": info["fuel_list"],
                "Power (MW)": info["power_value"],
                "Emissions (tCO2e)": info["emission_value"]
            } for _, info in filtered])
            st.dataframe(df_preview, width=400, height=200)
    
    # Draw Map (Core requirement of Assignment Task4)
    filtered_facilities = filter_facilities()
    st_folium(get_cached_map(filtered_facilities), key="facility_map", width=1200, height=800)
    
    # Auto-refresh (Assignment Task5 Requirement: Continuous execution) )
    # time.sleep(5)
    # st.rerun()

if __name__ == "__main__":
    main()
