from __future__ import annotations

import atexit
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised in dependency-light test envs
    class _MissingMQTTClient:
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("paho-mqtt is required for MQTT publishing")

    mqtt = SimpleNamespace(
        Client=_MissingMQTTClient,
        MQTT_ERR_SUCCESS=0,
        CallbackAPIVersion=SimpleNamespace(VERSION1=1),
    )

from src.shared.mqtt_topics import MQTT_PUBLISH_TOPIC_TEMPLATE as DEFAULT_PUBLISH_TOPIC_TEMPLATE
from src.shared.paths import data_path


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


BROKER = os.getenv("MQTT_BROKER") or os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT") or os.getenv("MQTT_BROKER_PORT", "1883"))
USERNAME = os.getenv("MQTT_USERNAME") or None
PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_TLS = os.getenv("MQTT_TLS", "false").strip().lower() in {"1", "true", "yes", "on"}
CLIENT_ID = "comp5339-publisher"
PUBLISH_TOPIC_TEMPLATE = (
    os.getenv("MQTT_PUBLISH_TOPIC_TEMPLATE")
    or DEFAULT_PUBLISH_TOPIC_TEMPLATE
)
PUBLISH_DURATION_SECONDS = max(0, int(os.getenv("PUBLISH_DURATION_SECONDS", "0")))
TICK = 0.100
TICK_NS = int(TICK * 1e9)
POLL_SECONDS = 5
MEASURE_CSV = data_path("data_for_publish.csv")


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


def normalize_ts(ts: str) -> str:
    return ts.replace(" ", "T")


def load_measure_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        ts_iso = normalize_ts(r["timestamp"])
        r["_ts_iso"] = ts_iso
        r["_ts_dt"] = datetime.fromisoformat(ts_iso)
        r["facility_code"] = r["facility_code"]
        r["facility_name"] = r["facility_name"]
        r["state"] = r["state"] if r["state"] else None
        r["fuel_list"] = r["fuel_list"] if r["fuel_list"] else None
        r["power_value"] = float(r["Power (MW)"]) if r["Power (MW)"] else None
        r["emission_value"] = float(r["Emissions (tonnes)"]) if r["Emissions (tonnes)"] else None
        r["price_per_mwh"] = float(r["Price ($/MWh)"]) if r["Price ($/MWh)"] else None
        r["demand_mw"] = float(r["Demand (MW)"]) if r["Demand (MW)"] else None
        r["lat"] = float(r["lat"]) if r["lat"] else None
        r["lng"] = float(r["lng"]) if r["lng"] else None
        r["unit"] = {"power_value": "MW", "emission_value": "tCO2e"}
    rows.sort(key=lambda r: (r["_ts_dt"], r["facility_code"]))
    return rows


def make_client():
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=CLIENT_ID, clean_session=False)
    else:
        client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    if MQTT_TLS:
        client.tls_set()
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


def safe_publish_stream(client, topic, payload, qos=1, retain=False):
    data = json.dumps(payload, ensure_ascii=False)
    info = client.publish(topic, data, qos=qos, retain=retain)
    if getattr(info, "rc", 0) != mqtt.MQTT_ERR_SUCCESS:
        return False
    try:
        info.wait_for_publish(timeout=5)
    except Exception:
        return False
    return info.is_published()


def publish_new_since(client, all_rows, state, deadline_ns: int | None = None):
    last_ts = state.get("last_ts")
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
        if deadline_ns is not None and perf_counter_ns() >= deadline_ns:
            print("[Main] Timed publisher deadline reached during batch.")
            return False

        code = r["facility_code"]
        target_ns = t0_ns + (step + 1) * TICK_NS
        now_ns = perf_counter_ns()
        if now_ns > target_ns:
            step = (now_ns - t0_ns) // TICK_NS
            target_ns = t0_ns + (step + 1) * TICK_NS

        if deadline_ns is not None and target_ns >= deadline_ns:
            print("[Main] Timed publisher deadline reached during batch.")
            return False

        sleep_until_ns(target_ns)
        step += 1

        if deadline_ns is not None and perf_counter_ns() >= deadline_ns:
            print("[Main] Timed publisher deadline reached during batch.")
            return False

        next_seq = state.get("seq", 0) + 1
        payload = {
            "seq": next_seq,
            "facility_code": code,
            "facility_name": r["facility_name"],
            "timestamp": r["_ts_iso"],
            "state": r["state"],
            "fuel_list": r["fuel_list"],
            "power_value": r["power_value"],
            "emission_value": r["emission_value"],
            "price_per_mwh": r["price_per_mwh"],
            "demand_mw": r["demand_mw"],
            "lat": r["lat"],
            "lng": r["lng"],
            "unit": r["unit"],
            "sent_mono_ns": perf_counter_ns(),
            "slot_mono_ns": target_ns,
        }
        topic = PUBLISH_TOPIC_TEMPLATE.format(facility_code=code)
        if not safe_publish_stream(client, topic, payload, qos=1, retain=False):
            print(f"[STREAM] Publish failed for {code}, will retry on next poll.")
            break

        state["seq"] = next_seq
        state["last_ts"] = r["_ts_dt"]
        state["last_fac"] = code

    return True


def wait_for_connection(client, attempts: int = 30, delay_seconds: float = 0.5) -> bool:
    print("[Main] Waiting for MQTT connection...")
    for _ in range(attempts):
        if client.is_connected():
            return True
        time.sleep(delay_seconds)
    return False


def run_publisher_loop(
    csv_path: Path = MEASURE_CSV,
    *,
    poll_seconds: int = POLL_SECONDS,
    duration_seconds: int | None = None,
) -> None:
    client = None
    effective_duration_seconds = PUBLISH_DURATION_SECONDS if duration_seconds is None else max(0, duration_seconds)
    deadline_ns = None if effective_duration_seconds <= 0 else perf_counter_ns() + int(effective_duration_seconds * 1e9)
    try:
        try:
            client = make_client()
        except OSError as exc:
            print(f"[Main] MQTT connect failed for {BROKER}:{PORT}: {exc}")
            raise SystemExit(1) from exc
        if not wait_for_connection(client):
            print("[Main] MQTT connect timeout, please check broker.")
            raise SystemExit

        if deadline_ns is None:
            print(f"[Main] Connected, starting stream with tick={TICK}s")
        else:
            print(
                f"[Main] Connected, starting timed stream with tick={TICK}s "
                f"for {effective_duration_seconds} seconds"
            )

        rows = load_measure_rows(csv_path)
        state = {"seq": 0, "last_ts": None, "last_fac": ""}

        while True:
            keep_running = publish_new_since(client, rows, state, deadline_ns=deadline_ns)
            if keep_running is False:
                break
            if deadline_ns is None:
                time.sleep(poll_seconds)
                continue

            remaining_ns = deadline_ns - perf_counter_ns()
            if remaining_ns <= 0:
                print(f"[Main] Timed publisher duration reached after {effective_duration_seconds} seconds.")
                break
            time.sleep(min(poll_seconds, remaining_ns / 1e9))
    finally:
        if client is not None:
            try:
                client.disconnect()
            except Exception as exc:
                print(f"[Main] MQTT disconnect error: {exc}")
            try:
                client.loop_stop()
            except Exception as exc:
                print(f"[Main] MQTT loop_stop error: {exc}")
        print("[Main] Publisher exited")
