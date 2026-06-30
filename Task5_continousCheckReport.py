
# -*- coding: utf-8 -*-
"""
COMP5339 MQTT Publisher (fixed)
- Reads facilities from facility_list.csv
- Streams consolidated_data_cleaned.csv rows per facility_code
- Publishes:
    comp5339/task123/facility_info/{facility_code}   (retained, once per run)
    comp5339/task123/measurements/{facility_code}    (streaming)
Columns expected:
  consolidated_data_cleaned.csv: timestamp, Power (MW), Emissions (tonnes), facility_code, Price ($/MWh), Demand (MW)
  facility_list.csv           : facility_code, facility_name, lat, lng
"""
# subscriber_interval_check.py
# 用法:
#   python subscriber_interval_check.py --host localhost --port 1883 \
#       --topic "comp5339/task123/measurements/+" --seconds 70 --expect 0.1 --tolerance 0.02

import argparse, time, json, statistics
from collections import defaultdict
import paho.mqtt.client as mqtt

def pct(sorted_list, q):
    if not sorted_list: return None
    i = (len(sorted_list)-1)*q
    lo, hi = int(i), min(int(i)+1, len(sorted_list)-1)
    w = i - lo
    return sorted_list[lo]*(1-w) + sorted_list[hi]*w

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", default="comp5339/task123/measurements/+")
    ap.add_argument("--seconds", type=int, default=70, help="采样时长（建议 ≥70s）")
    ap.add_argument("--expect", type=float, default=0.1, help="期望间隔(秒)")
    ap.add_argument("--tolerance", type=float, default=0.02, help="容差(±秒)，如0.02=>[0.08,0.12]")
    args = ap.parse_args()

    # --- 统计容器 ---
    per_topic_last_arrival = {}            # 每主题上一次“到达时间”（monotonic，订阅侧）
    per_topic_deltas_arrival = defaultdict(list)

    global_last_arrival = None             # 全局上一次“到达时间”
    global_deltas_arrival = []             # 全局按“到达时间”的间隔

    # 新增：发布侧 sent_mono_ns 统计（跨主题“全局”）
    last_sent_s = None                     # 上一次“发布侧单调时钟（秒）”
    global_deltas_sent = []                # 全局按“发送时间”的间隔（最客观）

    seq_prev = None
    total_msgs = 0

    low, high = args.expect - args.tolerance, args.expect + args.tolerance

    def on_message(client, userdata, msg):
        nonlocal global_last_arrival, last_sent_s, seq_prev, total_msgs
        now = time.monotonic()
        total_msgs += 1

        # 尝试解析 JSON
        payload = None
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            pass

        # --- 优先使用“发布侧时间戳 sent_mono_ns”计算间隔（更客观） ---
        if isinstance(payload, dict):
            send_ns = payload.get("sent_mono_ns")  # 由 publisher 注入
            if isinstance(send_ns, (int, float)):
                send_s = send_ns / 1e9
                if last_sent_s is not None:
                    global_deltas_sent.append(send_s - last_sent_s)
                last_sent_s = send_s

        # --- 回退/对照：到达时间的全局间隔 ---
        if global_last_arrival is not None:
            global_deltas_arrival.append(now - global_last_arrival)
        global_last_arrival = now

        # --- 回退/对照：到达时间的每主题间隔 ---
        t = msg.topic
        if t in per_topic_last_arrival:
            per_topic_deltas_arrival[t].append(now - per_topic_last_arrival[t])
        per_topic_last_arrival[t] = now

        # --- 序号连续性（可选）---
        if isinstance(payload, dict) and "seq" in payload:
            seq = payload["seq"]
            if seq_prev is not None and seq != seq_prev + 1:
                print(f"[WARN] seq gap: got {seq}, prev {seq_prev}")
            seq_prev = seq

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    client.subscribe(args.topic, qos=0)
    client.loop_start()

    print(f"[INFO] Sampling {args.seconds}s on topic '{args.topic}' ...")
    time.sleep(args.seconds)

    client.loop_stop()
    client.disconnect()

    # --- 报告工具 ---
    def summarize(label, lst):
        lst_sorted = sorted(lst)
        within = sum(1 for x in lst if low <= x <= high)
        return (
            f"{label}: n={len(lst)}, mean={statistics.mean(lst):.4f}s, "
            f"min={min(lst):.4f}, max={max(lst):.4f}, "
            f"p50={pct(lst_sorted,0.50):.4f}, p90={pct(lst_sorted,0.90):.4f}, "
            f"p95={pct(lst_sorted,0.95):.4f}, p99={pct(lst_sorted,0.99):.4f}, "
            f"within[{low:.3f},{high:.3f}]={within/len(lst)*100:.1f}%"
        )

    print("\n=== Timing Report ===")
    print(f"Total messages received: {total_msgs}")

    # 1) 首先报告“发布侧时间戳”的全局节拍（首选）
    if global_deltas_sent:
        print(summarize("GLOBAL (sender-side, sent_mono_ns)", global_deltas_sent))
    else:
        print("GLOBAL (sender-side): No deltas (publisher 可能未注入 sent_mono_ns)")

    # 2) 报告“到达时间”的全局节拍（对照）
    if global_deltas_arrival:
        print(summarize("GLOBAL (arrival)", global_deltas_arrival))
    else:
        print("GLOBAL (arrival): No deltas")

    # 3) 报告“到达时间”的每主题节拍（对照）
    any_topic = False
    for t, lst in per_topic_deltas_arrival.items():
        if not lst: continue
        any_topic = True
        print(summarize(f"TOPIC {t} (arrival)", lst))
    if not any_topic:
        print("PER-TOPIC (arrival): No deltas")

    # 4) 最终判定：优先按“发布侧时间戳”的全局节拍
    candidate = global_deltas_sent if global_deltas_sent else global_deltas_arrival
    if candidate:
        within = sum(1 for x in candidate if low <= x <= high)
        ok = (within / len(candidate) >= 0.95)
        print("\nRESULT:", "PASS ✅" if ok else "FAIL ❌")
    else:
        print("\nRESULT: INDETERMINATE (没有可计算间隔的数据)")
        
if __name__ == "__main__":
    main()



