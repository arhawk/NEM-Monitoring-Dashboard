import requests
import pandas as pd
import numpy as np
from datetime import datetime
import json
from io import StringIO
import pytz
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os

#=============================== Task 1 scrapying facility data from Open Electricity API ================================#
#=========================================================================================================================#
API_KEY = "oe_3ZWfWHmHqrpYEUbj7vff5Ey5"

CACHE_FILE = "data/facility_data_cache.json"
# Thread lock to ensure safe cache writing
cache_lock = threading.Lock()

def load_cache():
    """Load cached data from JSON file and restore datetime/DataFrame objects"""
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
            for key, value in data.items():
                parts = key.split('|')
                if len(parts) != 4:
                    print(f"Invalid cache key: {key}, skipped")
                    continue
                # Parse timestamps and restore DataFrames
                value['date_start'] = datetime.fromisoformat(value['date_start'])
                value['date_end'] = datetime.fromisoformat(value['date_end'])
                consolidated_io = StringIO(value['consolidated_data'])
                value['consolidated_data'] = pd.read_json(consolidated_io, orient='split')
            return data
    except FileNotFoundError:
        return {}


def save_cache(cache):
    """Save cache to JSON (thread-safe), converting non-serializable objects first"""
    with cache_lock:  # Prevent race conditions in multi-threading
        serializable_cache = {}
        for key, value in cache.items():
            serializable_cache[key] = {
                'date_start': value['date_start'].isoformat(),
                'date_end': value['date_end'].isoformat(),
                'consolidated_data': value['consolidated_data'].to_json(orient='split')
            }
        with open(CACHE_FILE, 'w') as f:
            json.dump(serializable_cache, f, indent=2)


def create_session():
    """Create a reusable HTTP session to reduce connection overhead"""
    session = requests.Session()
    session.headers = {"Authorization": f"Bearer {API_KEY}"} 
    return session


def fetch_response(session, API, params=None):
    """Fetch HTTP response with error handling"""
    try:
        response = session.get(API, params=params)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as errh:
        if errh.response.status_code == 416:  # Range not satisfiable
            return None
    except Exception as err:
        print(f"Request error: {err}")
        return None


def fetch_facility_list():
    """Retrieve list of facilities from API (filtered by network 'NEM')"""
    session = create_session()
    params = {"network_id": "NEM"}
    API = "https://api.openelectricity.org.au/v4/facilities/"
    response = fetch_response(session, API, params)
    session.close()
    
    if not response:
        return pd.DataFrame()
    
    # Extract facility details (code, name, location)
    rows = []
    for facility in response.json()["data"]:
        row = {
            "facility_code": facility["code"],
            "facility_name": facility["name"]
        }
        if "location" in facility:
            row["lat"] = facility["location"]["lat"]
            row["lng"] = facility["location"]["lng"]
        rows.append(row)
    return pd.DataFrame(rows)


def _get_data(response, data_type):
    """Parse raw API response into structured DataFrame for a specific metric type"""
    rows = []
    data_dict = {"power": 0, "emissions": 1, "price": 0, "demand": 1}
    sydney_tz = pytz.timezone('Australia/Sydney')  # Sydney timezone
    
    try:
        json_data = response.json()
        for unit in json_data["data"][data_dict[data_type]]["results"]:
            for time_slot in unit["data"]:
                ts_raw, value = time_slot
                ts_datetime = None  # Initialize timestamp object
                
                # 1. Handle Unix timestamp (int/float in milliseconds)
                if isinstance(ts_raw, (int, float)):
                    # Convert milliseconds to seconds, then to Sydney timezone datetime
                    ts_datetime = datetime.fromtimestamp(ts_raw / 1000, tz=sydney_tz)
                
                # 2. Handle ISO8601 string (may or may not have timezone)
                else:
                    # Parse raw string to datetime (preserves existing timezone if any)
                    ts_parsed = datetime.fromisoformat(ts_raw)
                    
                    # Case 1: Parsed datetime has no timezone → add Sydney timezone
                    if ts_parsed.tzinfo is None:
                        ts_datetime = sydney_tz.localize(ts_parsed, is_dst=None)
                    
                    # Case 2: Parsed datetime has a timezone → convert to Sydney timezone
                    else:
                        ts_datetime = ts_parsed.astimezone(sydney_tz)
                
                # Convert to ISO8601 format with Sydney timezone (e.g. "2025-10-25T00:00:00+10:00")
                ts_iso = ts_datetime.isoformat()
                
                rows.append({
                    "code": unit["name"],
                    "timestamp": ts_iso,
                    "value": value
                })
        
        # Convert to DataFrame and parse timestamps with ISO8601 format
        data = pd.DataFrame(rows)
        # Use format='ISO8601' to correctly parse timezone-aware strings
        data["timestamp"] = pd.to_datetime(data["timestamp"], format='ISO8601', utc=False)
        return data.groupby("timestamp")["value"].sum().reset_index()
    
    except Exception as e:
        print(f"Data parsing error: {e}")
        return pd.DataFrame()


def _get_params(response):
    """Extract metric parameters from the request URL"""
    parsed_url = urlparse(response.request.url)
    request_params = parse_qs(parsed_url.query)
    return request_params["metrics"][0], request_params["metrics"][1]


def fetch_data(response, fCode):
    """Merge two metric datasets (e.g., power + emissions) for a facility"""
    if response is None:
        return pd.DataFrame()
    
    # Map API metrics to readable column names
    colnames = {
        "power": "Power (MW)", 
        "emissions": "Emissions (tonnes)", 
        "price": "Price ($/MWh)", 
        "demand": "Demand (MW)"
    }
    
    # Extract and parse both metrics from the response
    col1, col2 = _get_params(response)
    data1 = _get_data(response, col1)
    data2 = _get_data(response, col2)
    
    # Rename columns and merge datasets
    data1.rename(columns={"value": colnames[col1]}, inplace=True)
    data2.rename(columns={"value": colnames[col2]}, inplace=True)
    consolidated_data = pd.merge(data1, data2, on="timestamp", how="outer")
    consolidated_data['facility_code'] = fCode  # Add facility identifier
    return consolidated_data


def process_facility(fCode, date_start, date_end, cache):
    """Process data for a single facility (thread-safe), using cache when possible"""
    print(f"Processing facility: {fCode}")
    # Define data sources (facility-specific vs. market-wide metrics)
    data_sources = {
        "facility": {
            "api_url": "https://api.openelectricity.org.au/v4/data/facilities/NEM",
            "metrics": ["power", "emissions"]
        },
        "market": {
            "api_url": "https://api.openelectricity.org.au/v4/market/network/NEM",
            "metrics": ["price", "demand"]
        }
    }
    
    source_data = {}
    session = create_session()  # One session per thread to avoid conflicts

    try:
        for source_type, config in data_sources.items():
            # Create unique cache key for this request
            cache_key = f"{source_type}|{fCode}|{date_start.isoformat()}|{date_end.isoformat()}"
            
            # Use cached data if available
            if cache_key in cache:
                source_data[source_type] = cache[cache_key]['consolidated_data']
                continue
            
            # Fetch new data if cache miss
            params = {
                "facility_code": fCode,
                "metrics": config["metrics"],
                "interval": "5m",  # 5-minute granularity
                "date_start": date_start,
                "date_end": date_end
            }
            response = fetch_response(session, config["api_url"], params)
            source_df = fetch_data(response, fCode)
            
            # Update cache with new data (thread-safe)
            if not source_df.empty:
                with cache_lock:
                    cache[cache_key] = {
                        "date_start": date_start,
                        "date_end": date_end,
                        "consolidated_data": source_df
                    }
            
            source_data[source_type] = source_df

        # Merge facility and market data
        facility_df = source_data["facility"]
        market_df = source_data["market"]
        
        if not facility_df.empty and not market_df.empty:
            merged_df = pd.merge(facility_df, market_df, on=["timestamp", "facility_code"], how="outer")
        elif not facility_df.empty:
            merged_df = facility_df
        elif not market_df.empty:
            merged_df = market_df
        else:
            merged_df = pd.DataFrame()
        
        return merged_df

    finally:
        session.close()  # Ensure session is closed after processing


def main():
    # Load existing cache
    cache = load_cache()
    
    # Fetch list of facilities
    facility_list = fetch_facility_list()
    if facility_list.empty:
        print("No facilities retrieved, exiting")
        return

    # Define date range for data collection
    date_start = datetime(2025, 10, 24, 23, 0, 0)
    date_end = datetime(2025, 10, 31, 22, 59, 59)

    # Collect results from all facilities
    all_merged_dfs = []
    max_workers = 15  # Adjust based on API rate limits
    
    # Process facilities in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_facility, fCode, date_start, date_end, cache): fCode
            for fCode in facility_list["facility_code"]
        }
        
        # Handle completed tasks
        for future in as_completed(futures):
            fCode = futures[future]
            try:
                merged_df = future.result()
                if not merged_df.empty:
                    all_merged_dfs.append(merged_df)
            except Exception as e:
                print(f"Error processing facility {fCode}: {e}")

    # Combine all facility data into a single dataset
    consolidated_data = pd.concat(all_merged_dfs, ignore_index=True) if all_merged_dfs else pd.DataFrame()

    # Save cache after all tasks complete
    save_cache(cache)

    # Export results
    print("All data processed!")
    print(f"Total facilities processed: {len(facility_list)}")
    print(f"Total rows after merging: {len(consolidated_data)}")
    facility_list.to_csv("data/facility_list.csv", index=False)
    consolidated_data.to_csv("data/consolidated_data_total.csv", index=False)

file_path = './data/consolidated_data_total.csv'

# if the consolidated data file does not exist, run main() to fetch and process data
if not os.path.exists(file_path):
    import pytz
    main()

#================================================ Task 2 data preprocessing ==============================================#
#=========================================================================================================================#

data =pd.read_csv('data/consolidated_data_total.csv')

# 1 convert timestamp to datetime type（+10:00 is Australian Eastern time）
data['timestamp'] = pd.to_datetime(data['timestamp'], utc=False) 
data.head()

# 2 Count negative values (excluding NaN, as NaN is not considered a negative value)
# Drop NaN first, then filter values < 0 and count their occurrences
power_neg_count = data['Power (MW)'].dropna()[data['Power (MW)'].dropna() < 0].shape[0]
emission_neg_count = data['Emissions (tonnes)'].dropna()[data['Emissions (tonnes)'].dropna() < 0].shape[0]

print("Number of negative values in Power (MW) before processing (excluding NaN):", power_neg_count)
print("Number of negative values in Emissions (tonnes) before processing (excluding NaN):", emission_neg_count)


# Replace negative values with 0 (only affect values < 0; NaN remains unchanged)
# Use mask() to replace values where the condition (x < 0) is True with 0
data['Power (MW)'] = data['Power (MW)'].mask(data['Power (MW)'] < 0, 0)
data['Emissions (tonnes)'] = data['Emissions (tonnes)'].mask(data['Emissions (tonnes)'] < 0, 0)


# Verify the result: negative values should be replaced with 0 (excluding NaN)
power_neg_count_after = data['Power (MW)'].dropna()[data['Power (MW)'].dropna() < 0].shape[0]
emission_neg_count_after = data['Emissions (tonnes)'].dropna()[data['Emissions (tonnes)'].dropna() < 0].shape[0]

print("Number of negative values in Power (MW) after processing (excluding NaN):", power_neg_count_after)  # Should be 0
print("Number of negative values in Emissions (tonnes) after processing (excluding NaN):", emission_neg_count_after)  # Should be 0

# 3 Handle missing values with vectorized approach

def fill_missing_half_ffill_bfill(series):
    """
    Vectorized processing for missing values in a single column:
    - For continuous missing segments: Fill first half with ffill, second half with bfill.
    - Keep fully missing segments as NaN (do not fill with 0).
    
    Args:
        series (pd.Series): Input column (e.g., Power (MW) or Emissions (tonnes))
        
    Returns:
        pd.Series: Column with missing values processed (NaN retained for fully missing segments)
    """
    # Mark non-missing and missing values (index aligns with the original series)
    non_na = series.notna()
    missing = ~non_na
    original_index = series.index  # Preserve original index for alignment later
    
    # If the entire series is missing (all NaN), return a copy to avoid modification; filtered later
    if series.isna().all():
        return series.copy()
    
    # Generate IDs for continuous missing segments:
    # - Non-missing values are assigned cumulative counts (unique for each segment)
    # - Missing values retain segment IDs; non-missing values are set to NaN
    segment_id = non_na.cumsum()
    segment_id_missing = segment_id.where(missing, np.nan)
    
    # Calculate 1) index of each missing value within its segment, 2) total length of each segment
    # Reindex to ensure alignment with the original series (fill gaps with NaN)
    within_segment_idx = segment_id_missing.groupby(segment_id_missing).transform(
        lambda x: np.arange(1, len(x) + 1)  # Assign 1,2,... to missing values in the same segment
    ).reindex(original_index, fill_value=np.nan)
    
    segment_length = segment_id_missing.groupby(segment_id_missing).transform(
        'count'  # Total number of missing values in each segment
    ).reindex(original_index, fill_value=np.nan)
    
    # Fill logic: ffill for first half, bfill for second half
    # (Fully missing segments are already returned early, so no need to handle here)
    ffill_series = series.ffill()  # Forward fill (carry last non-missing value forward)
    bfill_series = series.bfill()  # Backward fill (carry next non-missing value backward)
    
    # Identify which missing values belong to the first half of their segment
    is_first_half = (within_segment_idx <= (segment_length // 2)) & missing
    
    # Combine results:
    # - Keep non-missing values as original
    # - Fill first half of missing segments with ffill, second half with bfill
    filled_values = np.where(
        non_na,  # Condition 1: Non-missing values
        series,  # Action: Retain original value
        np.where(
            is_first_half,  # Condition 2: Missing values in first half of segment
            ffill_series,  # Action: Use forward fill
            bfill_series   # Action: Use backward fill
        )
    )
    
    # Return processed series with original index preserved
    return pd.Series(filled_values, index=original_index, name=series.name)


def handle_missing_values_fast(group):
    """
    Fast missing value handling for a single facility's data:
    - Strictly exclude facilities with full missing values (both Power and Emissions are all NaN).
    - Only process missing values for non-full-missing facilities.
    
    Args:
        group (pd.DataFrame): Grouped data for a single facility
        
    Returns:
        pd.DataFrame: Processed data (empty DataFrame if facility is fully missing)
    """
    # Check if both Power and Emissions are COMPLETELY missing (all values are NaN)
    power_all_na = group['Power (MW)'].isna().all()
    emission_all_na = group['Emissions (tonnes)'].isna().all()
    
    # If fully missing: Return empty DataFrame (no columns/rows) to ensure filtering later
    if power_all_na and emission_all_na:
        return pd.DataFrame()
    
    # Process missing values for non-full-missing facilities
    group['Power (MW)'] = fill_missing_half_ffill_bfill(group['Power (MW)'])
    group['Emissions (tonnes)'] = fill_missing_half_ffill_bfill(group['Emissions (tonnes)'])
    
    return group

# Execute missing value processing
# - Group data by facility; disable group keys to reduce overhead; use observed=True for efficiency
data = data.groupby('facility_code', group_keys=False, observed=True).apply(handle_missing_values_fast)

# Completely remove all empty rows (including empty DataFrames from fully missing facilities)
df_cleaned = data.dropna(how='all')

# Validation: Ensure fully missing facilities are excluded and missing values are processed
print("Total number of facilities after processing:", df_cleaned['facility_code'].nunique())
print("Number of missing values in Power (MW) after processing:", df_cleaned['Power (MW)'].isna().sum())
print("Number of missing values in Emissions (tonnes) after processing:", df_cleaned['Emissions (tonnes)'].isna().sum())
print("Number of missing values in Price ($/MWh) after processing:", df_cleaned['Price ($/MWh)'].isna().sum())
print("Number of missing values in Demand (MW) after processing:", df_cleaned['Demand (MW)'].isna().sum())
print("Total rows after cleaning:", df_cleaned.shape[0])
df_cleaned.to_csv('data/consolidated_data_cleaned.csv', index=False)

#===================================== Task 2.5 Align Consildate_data with A1  =============================================#
#=========================================================================================================================#
# Merge with A1 Datas
import pandas as pd

df1 = pd.read_csv('data/facility_list.csv')
df2 = pd.read_csv('data/NGER_data_aug.csv')
df3 = pd.read_csv('data/CER_data_aug.csv')

def combine_matching(df1, df2, left_on, right_on, keep):
    df2 = df2.drop(columns=['lat','lng'])
    matches = []
    for idx1, row1 in df1.iterrows():
        # Find rows in the right table where the matching column contains the value from the left table (fuzzy match)
        matched_df2 = df2[df2[right_on].str.contains(row1[left_on], na=False)]
        if not matched_df2.empty:
            # If there is a match: record all matching indices from the right table
            for idx2 in matched_df2.index:
                matches.append({"df1_idx": idx1, "df2_idx": idx2})
        else:
            if keep:
                # If there is no match: record the right table index as None to ensure all rows from the left table are kept
                matches.append({"df1_idx": idx1, "df2_idx": None})
    
    # Convert to DataFrame and merge the left and right tables (left join to keep all rows from df1)
    match_df = pd.DataFrame(matches)
    result = pd.merge(
        match_df,
        df1.reset_index().rename(columns={"index": "df1_idx"}),
        on="df1_idx",
        how="left"  # Left join: keep all rows from df1
    ).merge(
        df2.reset_index().rename(columns={"index": "df2_idx"}),
        on="df2_idx",
        how="left"  # Left join: only merge matching rows from df2, fill with NaN if no match
    )
    
    # Drop temporary index columns
    result = result.drop(columns=["df1_idx", "df2_idx"])
    return result

# Merge facility_list with NGER_data
tmp_df = combine_matching(df1, df2, left_on='facility_name', right_on='facilityName', keep=False)
# Merge the result with CER_data
tmp_df2 = combine_matching(tmp_df, df3, left_on='facility_name', right_on='powerStation', keep=True)
# Select required columns
tmp_df3 = tmp_df2[["facility_code", "facility_name","primaryFuel", "state_x", "lat", "lng", "fuelSource"]]
tmp_df3 = tmp_df3.rename(columns={"state_x": "state", "fuelSource": "futureFuelSource"})
# Drop the year since they are all the same
tmp_df3_clean = tmp_df3.drop_duplicates()

# Create a fuel list mapped by facility name
def combine_fuels(group):
    fuel_list = group['primaryFuel'].tolist()
    future_fuels = group['futureFuelSource'].dropna().tolist()
    fuel_list.extend(future_fuels)
    return fuel_list

# Group by specified columns and apply the custom function
grouped = tmp_df3_clean.groupby(
    ['facility_name', 'facility_code', 'lat', 'lng', 'state']
).apply(lambda x: combine_fuels(x)).reset_index(name='fuel_list')

# grouped.to_csv('data/facilityCode_Aligned_A1.csv', index=False)
# data = pd.read_csv('facility_list.csv')
merged_df = pd.merge(df_cleaned, grouped, on='facility_code', how='inner')
merged_df.to_csv('data/data_for_publish.csv', index=False)


#========================================== Task 3 mqtt server publisher  ================================================#
#=========================================================================================================================#
import os, json, time, csv, atexit, sys
from datetime import datetime
from time import perf_counter_ns
import paho.mqtt.client as mqtt

# -------- Windows: Improve timer precision to 1ms (ensure sleep accuracy) --------
if sys.platform.startswith("win"):
    import ctypes
    _winmm = ctypes.WinDLL("winmm")
    _winmm.timeBeginPeriod(1)
    @atexit.register
    def _restore_timer():
        try:
            _winmm.timeEndPeriod(1)
        except Exception:
            pass

# -------- Basic Configuration --------
BROKER = "127.0.0.1"
PORT = 1883
CLIENT_ID = "comp5339-publisher"   # Fixed ID for persistent session

TOPIC_MEAS = "comp5339/task123/measurements/{facility_code}"  # Only keep the measurement data topic

TICK = 0.100
TICK_NS = int(TICK * 1e9)
POLL_SECONDS = 5  # Define the missing polling interval in the original code

# Automatically locate the CSV file in the current folder
BASE_DIR = os.path.dirname(__file__)
MEASURE_CSV  = os.path.join(BASE_DIR, "data/data_for_publish.csv")  # Only keep the measurement data CSV

# -------- Accurate blocking until absolute time (nanoseconds) --------
def sleep_until_ns(target_ns: int, spin_ns: int = 5_000_000):
    while True:
        now_ns = perf_counter_ns()
        remain = target_ns - now_ns
        if remain <= 0:
            return
        if remain > spin_ns:
            time.sleep((remain - spin_ns) / 1e9)
        else:
            while perf_counter_ns() < target_ns:
                pass
            return

# -------- CSV Reading --------
def _safe_float(x):
    if x is None:
        return None
    s = str(x).strip()
    if s in ("", "NA", "N/A", "null", "None"):
        return None
    try:
        return float(s)
    except Exception:
        return None

def normalize_ts(ts: str) -> str:
    return ts.replace(" ", "T")

def load_measure_rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        ts_iso = normalize_ts(r["timestamp"])
        r["_ts_iso"] = ts_iso
        r["_ts_dt"]  = datetime.fromisoformat(ts_iso)  # Supports timezone offsets
        r["facility_code"]   = r["facility_code"]
        r["facility_name"]   = r["facility_name"]
        r["state"]           = r["state"] if r["state"] else None
        r["fuel_list"]       = r["fuel_list"] if r["fuel_list"] else None
        r["power_value"]     = float(r["Power (MW)"]) if r["Power (MW)"] else None
        r["emission_value"]  = float(r["Emissions (tonnes)"]) if r["Emissions (tonnes)"] else None
        r["price_per_mwh"]   = float(r["Price ($/MWh)"]) if r["Price ($/MWh)"] else None
        r["demand_mw"]       = float(r["Demand (MW)"]) if r["Demand (MW)"] else None
        r["lat"]       = float(r["lat"]) if r["lat"] else None
        r["lng"]       = float(r["lng"]) if r["lng"] else None
        r["unit"]            = {"power_value": "MW", "emission_value": "tCO2e"}
        # r["source"]          = os.path.basename(path)
    rows.sort(key=lambda r: (r["_ts_dt"], r["facility_code"])) 
    return rows

# -------- MQTT --------
def make_client():
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=CLIENT_ID, clean_session=False)
    else:
        client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.on_connect = lambda c, u, f, rc: print(f"[MQTT] connected rc={rc}")
    client.on_disconnect = lambda c, u, rc: print(f"[MQTT] disconnected rc={rc}")
    try:
        client.reconnect_delay_set(min_delay=1, max_delay=30)
    except Exception:
        pass
    client.max_inflight_messages_set(60)
    client.max_queued_messages_set(0)
    client.will_set("comp5339/task123/system/will", payload="publisher_offline", qos=1, retain=True)
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_start()
    return client

def safe_publish(client, topic, payload, qos=1, retain=False):
    data = json.dumps(payload, ensure_ascii=False)
    info = client.publish(topic, data, qos=qos, retain=retain)
    info.wait_for_publish(timeout=5)
    return getattr(info, "rc", 0) == mqtt.MQTT_ERR_SUCCESS and info.is_published()

def safe_publish_stream(client, topic, payload, qos=1, retain=False):
    data = json.dumps(payload, ensure_ascii=False)
    info = client.publish(topic, data, qos=qos, retain=retain)
    return getattr(info, "rc", 0) == mqtt.MQTT_ERR_SUCCESS

# -------- Publishing --------
def publish_new_since(client, all_rows, state):
    last_ts  = state.get("last_ts")
    last_fac = state.get("last_fac", "")

    def is_new(r):
        if last_ts is None: 
            return True
        if r["_ts_dt"] > last_ts:
            return True
        if r["_ts_dt"] == last_ts and r["facility_code"] > last_fac:
            return True
        return False

    cand = [r for r in all_rows if is_new(r)]
    cand.sort(key=lambda r: (r["_ts_dt"], r["facility_code"]))
    if not cand:
        print("[STREAM] No new records this round.")
        return

    print(f"[STREAM] Publishing {len(cand)} rows (since {(last_ts, last_fac)})")
    t0_ns, step = perf_counter_ns(), 0

    for r in cand:
        code = r["facility_code"]

        # Precise 0.1s absolute tick (if behind, don't catch up, jump to next tick directly)
        target_ns = t0_ns + (step + 1) * TICK_NS
        now_ns    = perf_counter_ns()
        if now_ns > target_ns:
            step = (now_ns - t0_ns) // TICK_NS
            target_ns = t0_ns + (step + 1) * TICK_NS

        sleep_until_ns(target_ns)
        step += 1

        state["seq"] = state.get("seq", 0) + 1
        payload = {
            "seq":            state["seq"],
            "facility_code":  code,
            "facility_name":  r["facility_name"],
            "timestamp":      r["_ts_iso"],
            "state":          r["state"],
            "fuel_list":      r["fuel_list"],
            "power_value":    r["power_value"],
            "emission_value": r["emission_value"],
            "price_per_mwh":  r["price_per_mwh"],
            "demand_mw":      r["demand_mw"],
            "lat":            r["lat"],
            "lng":            r["lng"], 
            "unit":           r["unit"],
            # "source":         r["source"],
            "sent_mono_ns":   perf_counter_ns(),   # Actual sending time
            "slot_mono_ns":   target_ns,           # Planned tick (exact 0.1s arithmetic sequence)
        }
        topic = TOPIC_MEAS.format(facility_code=code)
        safe_publish_stream(client, topic, payload, qos=1, retain=False)

        # —— Key: Advance the "cursor" only after successful publication —— #
        state["last_ts"]  = r["_ts_dt"]
        state["last_fac"] = code


# -------- main --------
if __name__ == "__main__":
    client = make_client()

    print("[Main] Waiting for MQTT connection...")
    for _ in range(30):
        if client.is_connected():
            break
        time.sleep(0.5)
    else:
        print("[Main] MQTT connect timeout, please check broker.")
        raise SystemExit

    print(f"[Main] Connected, starting stream with tick={TICK}s")
    rows  = load_measure_rows(MEASURE_CSV)
    state = {"seq": 0, "last_ts": None, "last_fac": ""} 

    while True:
        publish_new_since(client, rows, state)
        time.sleep(POLL_SECONDS)