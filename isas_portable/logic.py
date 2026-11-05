"""Observed motion RMS and provisional anomaly candidates; no motor diagnosis."""

import math
import statistics
from collections import deque


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def vector(value):
    if not isinstance(value, dict):
        return None
    result = [numeric(value.get(axis, value.get(axis.upper()))) for axis in "xyz"]
    return result if all(v is not None for v in result) else None


def seconds(value):
    if numeric(value) is not None:
        return float(value)
    if isinstance(value, str):
        from datetime import datetime
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return None


class Detector:
    def __init__(self, config):
        self.c = config
        self.samples = [deque(maxlen=20000) for _ in range(4)]
        self.temps = [None] * 4
        self.temp_received = [None] * 4
        self.temp_timestamp = [None] * 4
        self.baseline = None
        self.last_source_time = [None] * 4
        self.last_received = [None] * 4
        self.pending = {}
        self.context = {}
        self.context_received = None
        self.context_source = None
        self.invalid_samples = 0
        self.timestamp_errors = 0
        self.sensor_stream = None
        self.stream_conflicts = 0

    def reset(self):
        self.__init__(self.c)

    def ingest(self, packet, now):
        context = packet.get("flight_context", packet.get("pixhawk"))
        has_sensor_data = "imu" in packet or "arms" in packet or "temperature" in packet
        if not has_sensor_data:
            if isinstance(context, dict):
                self.context = context
                self.context_received = now
                self.context_source = packet.get("source", "legacy")
            return
        stream = (packet.get("source", "legacy"), packet.get("transport", {}).get("session"))
        if self.sensor_stream is None:
            self.sensor_stream = stream
        elif stream != self.sensor_stream:
            fresh = any(t is not None and now-t <= self.c["stale_s"] for t in self.last_received)
            if fresh:
                self.stream_conflicts += 1
                return
            self.reset()
            self.sensor_stream = stream
        # A rejected sensor stream must not overwrite the selected stream's
        # matching flight state (for example, a second MATLAB simulator).
        if isinstance(context, dict):
            self.context = context
            self.context_received = now
            self.context_source = packet.get("source", "legacy")
        timestamp = seconds(packet.get("timestamp"))
        arm_data = packet.get("arms") if isinstance(packet.get("arms"), dict) else {}
        imu_data = packet.get("imu") if isinstance(packet.get("imu"), dict) else {}
        temp_data = packet.get("temperature") if isinstance(packet.get("temperature"), dict) else {}
        for i in range(4):
            arm = arm_data.get(f"arm{i + 1}", {})
            arm = arm if isinstance(arm, dict) else {}
            accel = arm.get("accel_mps2") if "arms" in packet else imu_data.get(f"CH{i}")
            a = vector(accel)
            if a is None:
                self.invalid_samples += 1
            elif timestamp is None:
                self.timestamp_errors += 1
            else:
                previous = self.last_source_time[i]
                if previous is not None and timestamp <= previous:
                    self.timestamp_errors += 1
                else:
                    if previous is not None and timestamp - previous > self.c["stale_s"]:
                        self.samples[i].clear()
                    self.last_source_time[i] = timestamp
                    self.last_received[i] = now
                    self.samples[i].append((timestamp, a))
                    while self.samples[i] and timestamp - self.samples[i][0][0] > self.c["window_s"]:
                        self.samples[i].popleft()
            raw_temp = arm.get("temperature_c") if "arms" in packet else temp_data.get(f"S{i + 1}")
            temp = numeric(raw_temp)
            if temp is not None and -55 <= temp <= 125:
                self.temps[i] = temp
                self.temp_received[i] = now
                ts = packet.get("temperature_timestamp")
                if isinstance(ts, dict):
                    ts = ts.get(f"S{i + 1}")
                self.temp_timestamp[i] = seconds(ts)

    def set_baseline(self, now):
        if any(t is None or now - t > self.c["temperature_stale_s"] for t in self.temp_received):
            raise ValueError("Receive all four valid temperatures before setting the baseline")
        self.baseline = list(self.temps)
        self.pending.clear()

    def sustained(self, key, condition, now):
        if not condition:
            self.pending.pop(key, None)
            return False
        start = self.pending.setdefault(key, now)
        return now - start >= self.c["hold_s"]

    def snapshot(self, now):
        context_fresh = self.context_received is not None and now - self.context_received <= self.c["context_stale_s"]
        armed = self.context.get("armed") if context_fresh else None
        attitude = self.context.get("attitude_deg", self.context.get("attitude", {}))
        gyro = vector(self.context.get("angular_velocity_rad_s"))
        roll = numeric(attitude.get("roll")) if isinstance(attitude, dict) else None
        pitch = numeric(attitude.get("pitch")) if isinstance(attitude, dict) else None
        maneuver_known = context_fresh and gyro is not None and roll is not None and pitch is not None
        maneuver = maneuver_known and (math.sqrt(sum(v*v for v in gyro)) > self.c["max_gyro_rad_s"] or max(abs(roll), abs(pitch)) > self.c["max_pitch_roll_deg"])
        flight_eligible = not self.c["require_flight_context"] or (armed is True and maneuver_known and not maneuver)
        rows = []
        for i in range(4):
            samples = self.samples[i]
            fresh = self.last_received[i] is not None and now - self.last_received[i] <= self.c["stale_s"]
            span = samples[-1][0] - samples[0][0] if len(samples) > 1 else 0
            intervals = [b[0] - a[0] for a, b in zip(samples, list(samples)[1:])]
            dt = statistics.median(intervals) if intervals else None
            mean_dt = span / (len(samples) - 1) if len(samples) > 1 and span > 0 else None
            fs = 1 / mean_dt if mean_dt else None
            jitter = statistics.pstdev(intervals) / dt if len(intervals) > 1 else None
            gap_limit = max(4 * dt, 0.05) if dt else None
            large_gaps = sum(interval > gap_limit for interval in intervals) if gap_limit else 0
            gap_fraction = large_gaps / len(intervals) if intervals else None
            max_interval = max(intervals) if intervals else None
            # Isolated scheduler delays are reported but do not invalidate a full RMS window.
            gap = bool(max_interval and (max_interval > 0.2 or gap_fraction > 0.05))
            ready = fresh and len(samples) >= self.c["min_samples"] and span >= self.c["window_s"] * 0.8 and not gap
            rms = None
            if ready:
                mean = [statistics.fmean(v[1][axis] for v in samples) for axis in range(3)]
                rms = math.sqrt(statistics.fmean(sum((v[1][axis]-mean[axis])**2 for axis in range(3)) for v in samples))
            temp_fresh = self.temp_received[i] is not None and now - self.temp_received[i] <= self.c["temperature_stale_s"]
            if self.temp_timestamp[i] is not None and self.last_source_time[i] is not None:
                temp_fresh = temp_fresh and 0 <= self.last_source_time[i] - self.temp_timestamp[i] <= self.c["temperature_stale_s"]
            rows.append({"arm": i+1, "acceleration": samples[-1][1] if samples and fresh else None,
                         "rms": rms, "hz": fs, "nyquist_hz": fs/2 if fs else None,
                         "jitter_fraction": jitter, "gap_fraction": gap_fraction,
                         "max_interval_s": max_interval, "gap": gap, "ready": ready,
                         "temperature": self.temps[i] if temp_fresh else None,
                         "temperature_age_known": self.temp_timestamp[i] is not None,
                         "bandwidth_sufficient": bool(fs and fs > 2*self.c["intended_band_hz"][1]),
                         "temperature_delta": self.temps[i]-self.baseline[i] if temp_fresh and self.baseline else None})
        all_ready = all(r["ready"] for r in rows)
        rms_median = statistics.median(r["rms"] for r in rows) if all_ready else None
        all_temp = all(r["temperature_delta"] is not None for r in rows)
        temp_median = statistics.median(r["temperature_delta"] for r in rows) if all_temp else None
        for i, row in enumerate(rows):
            rv = row["rms"]-rms_median if all_ready else None
            rt = row["temperature_delta"]-temp_median if all_temp else None
            vib = self.sustained((i,"v"), all_ready and flight_eligible and rv > self.c["rms_relative_mps2"], now)
            thermal = self.sustained((i,"t"), rt is not None and rt > self.c["temperature_relative_c"], now)
            hot = self.sustained((i,"hot"), row["temperature"] is not None and row["temperature"] >= self.c["temperature_high_c"], now)
            status = "compound_candidate" if vib and (thermal or hot) else "vibration_candidate" if vib else "thermal_candidate" if thermal or hot else "observing"
            if not row["ready"]:
                status = "warming_up" if row["acceleration"] else "data_missing"
            elif not vib and not thermal and not hot and not flight_eligible:
                status = "maneuver" if maneuver else "disarmed" if armed is False else "context_missing"
            row.update({"relative_rms":rv,"relative_temperature":rt,"status":status,
                        "thermal_candidate":thermal or hot,"vibration_candidate":vib})
        return {"arms":rows,"flight_context":self.context if context_fresh else {},
                "flight_context_source":self.context_source if context_fresh else None,
                "context_fresh":context_fresh,"maneuver_known":maneuver_known,
                "flight_eligible":flight_eligible,"baseline_set":self.baseline is not None,
                "thresholds_validated":self.c["thresholds_validated"],
                "invalid_samples":self.invalid_samples,"timestamp_errors":self.timestamp_errors,
                "stream_conflicts":self.stream_conflicts,
                "metric":"window_demeaned_vector_rms_unfiltered"}
