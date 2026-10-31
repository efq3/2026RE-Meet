"""Forward existing stdout JSONL to a laptop, preserving an independent local log."""

import argparse
import json
import math
import queue
import random
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


def demo(rate):
    rng = random.Random(3)
    start = time.monotonic()
    n = 0
    while True:
        t = n / rate
        fault = 10 <= t % 35 < 25
        packet = {"timestamp":time.time(),"temperature_timestamp":time.time(),
                  "flight_context":{"armed":True,"flight_mode":"DEMO ONLY",
                                    "attitude_deg":{"roll":0,"pitch":0,"yaw":0},
                                    "angular_velocity_rad_s":{"x":0,"y":0,"z":0}},
                  "imu":{},"temperature":{},"simulation":True}
        for i in range(4):
            amplitude = 1.4 if i == 2 and fault else 0.07
            packet["imu"][f"CH{i}"] = {"X":amplitude*math.sin(2*math.pi*7*t)+rng.gauss(0,0.01),
                                                    "Y":-1.6+rng.gauss(0,0.01),"Z":9.7+rng.gauss(0,0.01)}
            packet["temperature"][f"S{i+1}"] = 25+i*0.2+(8 if i == 2 and fault else 0)
        yield json.dumps(packet)
        n += 1
        time.sleep(max(0, start+n/rate-time.monotonic()))


def main():
    parser = argparse.ArgumentParser(description="Pi JSONL -> ISAS laptop TCP")
    parser.add_argument("--host", required=True, help="Receiving laptop IPv4 address")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", default="pi-sensors")
    parser.add_argument("--local-log", type=Path)
    parser.add_argument("--file", type=Path, help="Replay JSONL file")
    parser.add_argument("--rate", type=float, default=20, help="Replay/demo packets per second; not sensor sampling rate")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="Python producer and its arguments, e.g. --command ../sensor.py")
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("rate must be positive")
    if sum(bool(v) for v in (args.file, args.demo, args.command)) > 1:
        parser.error("Choose one input: --file, --demo, --command, or stdin")
    log_path = args.local_log or Path(f"{args.source}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pending = queue.Queue(maxsize=2000)
    stop = threading.Event()
    stats = {"read":0,"dropped":0,"sent":0,"skipped":0}
    session = uuid.uuid4().hex
    process = None
    if args.command:
        process = subprocess.Popen([sys.executable,"-u",*args.command], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        lines = process.stdout
    elif args.file:
        lines = args.file.open(encoding="utf-8-sig")
    elif args.demo:
        lines = demo(args.rate)
    else:
        lines = sys.stdin

    def read_input():
        try:
            with log_path.open("a", encoding="utf-8", buffering=1) as local:
                for line in lines:
                    if stop.is_set():
                        break
                    try:
                        packet = json.loads(line)
                        if not isinstance(packet, dict) or not any(k in packet for k in ("imu","arms","pixhawk","flight_context")):
                            raise ValueError("Not a telemetry object")
                        # Preserve producer timestamps; never replace old samples with current time.
                        stats["read"] += 1
                        packet["source"] = args.source
                        packet["transport"] = {"session":session,"sequence":stats["read"],
                                               "network_dropped_before":stats["dropped"],
                                               "forwarded_unix":time.time(),"replay":bool(args.file)}
                        encoded = (json.dumps(packet, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
                    except (ValueError, TypeError):
                        stats["skipped"] += 1
                        continue
                    local.write(encoded.decode("utf-8"))
                    if pending.full():
                        try:
                            pending.get_nowait()
                            stats["dropped"] += 1
                        except queue.Empty:
                            pass
                    pending.put(encoded)
                    if args.file:
                        stop.wait(1/args.rate)
        except (OSError, UnicodeError) as error:
            print(f"Input/local log error: {error}", file=sys.stderr, flush=True)
        finally:
            stop.set()

    threading.Thread(target=read_input, daemon=True).start()
    connection = None
    last_report = 0
    print(f"Forwarding to {args.host}:{args.port}; local log: {log_path}", flush=True)
    try:
        while not stop.is_set() or not pending.empty():
            if connection is None:
                try:
                    connection = socket.create_connection((args.host,args.port), timeout=2)
                    connection.settimeout(2)
                    print("TCP connected", flush=True)
                except OSError as error:
                    print(f"TCP reconnecting: {error}", file=sys.stderr, flush=True)
                    time.sleep(1)
                    continue
            try:
                data = pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                connection.sendall(data)
                stats["sent"] += 1
            except OSError:
                stats["dropped"] += 1
                connection.close()
                connection = None
            if time.monotonic()-last_report > 5:
                print(json.dumps(stats), flush=True)
                last_report = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if connection:
            connection.close()
        if process:
            process.terminate()
            process.wait(timeout=5)
        print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
