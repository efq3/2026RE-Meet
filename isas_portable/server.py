"""Dependency-free TCP JSONL -> recorded logs + HTTP/SSE ISAS monitor."""

import argparse
import copy
import json
import math
import os
import queue
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from logic import Detector

ROOT = Path(__file__).resolve().parent
MAX_LINE = 262144


class State:
    def __init__(self, logdir):
        self.config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.detector = Detector(self.config)
        self.lock = threading.RLock()
        self.clients = set()
        self.sources = {}
        self.packets = 0
        self.invalid_lines = 0
        self.last_received = None
        self.display = None
        self.log_error = None
        self.stream_sequences = {}
        self.sequence_gaps = 0
        self.simulation = False
        self.replay = False
        self.ssh_status = "disabled"
        self.ssh_process = None
        self.test_injection = {
            "enabled": False,
            "rms_mps2": [0.0, 0.0, 0.0, 0.0],
            "frequency_hz": 30.0,
        }
        self.stop = threading.Event()
        self.last_log_flush = time.monotonic()
        logdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.raw_path = logdir / f"raw_{stamp}.jsonl"
        self.audit_path = logdir / f"receipt_{stamp}.jsonl"
        self.feature_path = logdir / f"features_{stamp}.jsonl"
        self.raw = self.raw_path.open("a", encoding="utf-8", buffering=1024 * 1024)
        self.audit = self.audit_path.open("a", encoding="utf-8", buffering=1024 * 1024)
        self.features = self.feature_path.open("a", encoding="utf-8", buffering=256 * 1024)
        self.config_path = logdir / f"config_{stamp}.json"
        self.config_path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    def session_files(self):
        return (self.raw_path, self.audit_path, self.feature_path, self.config_path)

    def ingest(self, packet, peer):
        with self.lock:
            now = time.monotonic()
            self.packets += 1
            self.last_received = now
            self.sources[packet.get("source", peer)] = time.time()
            transport = packet.get("transport")
            if isinstance(transport, dict):
                key = (packet.get("source", peer), transport.get("session"))
                sequence = transport.get("sequence")
                if isinstance(sequence, int) and not isinstance(sequence, bool):
                    previous = self.stream_sequences.get(key)
                    if previous is not None and sequence > previous:
                        self.sequence_gaps += max(0, sequence-previous-1)
                    self.stream_sequences[key] = sequence
                if "imu" in packet or "arms" in packet:
                    self.replay = transport.get("replay") is True
            if "imu" in packet or "arms" in packet:
                self.simulation = packet.get("simulation") is True
            try:
                encoded = json.dumps(packet, ensure_ascii=False, allow_nan=False)
                self.raw.write(encoded + "\n")
                self.audit.write(json.dumps({"packet":self.packets,"received_unix":time.time(),"peer":peer}) + "\n")
                if now - self.last_log_flush >= 1.0:
                    self.raw.flush()
                    self.audit.flush()
                    self.features.flush()
                    self.last_log_flush = now
            except OSError as error:
                self.log_error = str(error)
            self.detector.ingest(self.inject_vibration(packet), now)

    def configure_injection(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected a JSON object")
        enabled = request.get("enabled") is True
        values = request.get("rms_mps2", [0.0] * 4)
        frequency = request.get("frequency_hz", 30.0)
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError("rms_mps2 must contain four arm values")
        if isinstance(frequency, bool) or not isinstance(frequency, (int, float)) or not math.isfinite(frequency):
            raise ValueError("frequency_hz must be a finite number")
        if not 0 < frequency < 62.5:
            raise ValueError("frequency_hz must be between 0 and 62.5 Hz")
        parsed = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Each arm RMS must be a finite number")
            if not 0 <= value <= 20:
                raise ValueError("Each arm RMS must be between 0 and 20 m/s^2")
            parsed.append(float(value))
        self.test_injection = {
            "enabled": enabled,
            "rms_mps2": parsed,
            "frequency_hz": float(frequency),
        }
        # Do not mix samples from two test conditions in one RMS window.
        self.detector.reset()

    def inject_vibration(self, packet):
        setting = self.test_injection
        if not setting["enabled"] or packet.get("simulation") is not True:
            return packet
        imu = packet.get("imu")
        timestamp = packet.get("timestamp")
        if not isinstance(imu, dict) or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            return packet
        processed = copy.deepcopy(packet)
        direction = (0.78, 0.51, 0.36)
        magnitude = math.sqrt(sum(value * value for value in direction))
        direction = tuple(value / magnitude for value in direction)
        for arm in range(4):
            channel = processed["imu"].get(f"CH{arm}")
            if not isinstance(channel, dict):
                continue
            peak = math.sqrt(2.0) * setting["rms_mps2"][arm]
            phase = arm * math.pi / 7.0
            signal = peak * math.sin(2.0 * math.pi * setting["frequency_hz"] * float(timestamp) + phase)
            for axis, component in zip("XYZ", direction):
                value = channel.get(axis, channel.get(axis.lower()))
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    channel[axis] = float(value) + signal * component
        processed["test_injection"] = dict(setting)
        return processed

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            result = self.detector.snapshot(now)
            result.update({"received_unix":time.time(),"packets":self.packets,
                           "last_packet_age_s":now-self.last_received if self.last_received is not None else None,
                           "invalid_lines":self.invalid_lines,"sources":self.sources,
                           "sequence_gaps":self.sequence_gaps,
                           "simulation":self.simulation,"replay":self.replay,
                           "ssh_status":self.ssh_status,
                           "test_injection":dict(self.test_injection),
                           "raw_log":str(self.raw_path),"log_error":self.log_error})
            return result


class Receiver(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        while True:
            try:
                line = self.rfile.readline(MAX_LINE + 1)
                if not line or len(line) > MAX_LINE:
                    return
                try:
                    packet = json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
                    if not isinstance(packet, dict):
                        raise ValueError("Expected JSON object")
                    self.server.state.ingest(packet, self.client_address[0])
                except (ValueError, TypeError, UnicodeDecodeError, AttributeError):
                    with self.server.state.lock:
                        self.server.state.invalid_lines += 1
            except (OSError, TimeoutError):
                return


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class HTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class Web(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/isas_monitor.html"):
            self.respond(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path in ("/monitor.js", "/style.css"):
            kind = "text/javascript" if self.path.endswith("js") else "text/css"
            self.respond(200, (ROOT / "web" / self.path[1:]).read_bytes(), kind+"; charset=utf-8")
        elif self.path == "/api/status":
            self.respond(200, json.dumps(self.server.state.snapshot(), allow_nan=False).encode())
        elif self.path == "/api/log":
            with self.server.state.lock:
                self.server.state.raw.flush()
                size = self.server.state.raw_path.stat().st_size
                stream = self.server.state.raw_path.open("rb")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Disposition", 'attachment; filename="isas_raw.jsonl"')
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with stream:
                while size > 0:
                    data = stream.read(min(65536, size))
                    if not data:
                        break
                    self.wfile.write(data)
                    size -= len(data)
        elif self.path == "/api/logs.zip":
            with self.server.state.lock:
                self.server.state.raw.flush()
                self.server.state.audit.flush()
                self.server.state.features.flush()
                files = self.server.state.session_files()
            temporary = tempfile.NamedTemporaryFile(prefix="isas_session_", suffix=".zip", delete=False)
            temporary_path = temporary.name
            temporary.close()
            try:
                with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for path in files:
                        if path.exists():
                            archive.write(path, arcname=path.name)
                size = os.path.getsize(temporary_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="isas_session_logs.zip"')
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with open(temporary_path, "rb") as stream:
                    while True:
                        data = stream.read(65536)
                        if not data:
                            break
                        self.wfile.write(data)
            finally:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
        elif self.path == "/events":
            client = queue.Queue(maxsize=2)
            with self.server.state.lock:
                self.server.state.clients.add(client)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self.wfile.write(b"retry: 1000\n\n")
                self.wfile.flush()
                while True:
                    try:
                        data = client.get(timeout=10)
                        self.wfile.write(b"data: " + data + b"\n\n")
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
            except (OSError, ConnectionError):
                pass
            finally:
                with self.server.state.lock:
                    self.server.state.clients.discard(client)
        else:
            self.respond(404, b"Not found", "text/plain")

    def do_POST(self):
        # Local same-origin controls; prevent cross-site calibration/reset requests.
        if self.headers.get("Origin") not in (None, "http://" + self.headers.get("Host", "")):
            self.respond(403, b'{"error":"Origin rejected"}')
            return
        with self.server.state.lock:
            if self.path == "/api/baseline":
                try:
                    self.server.state.detector.set_baseline(time.monotonic())
                except ValueError as error:
                    self.respond(400, json.dumps({"error":str(error)}).encode())
                    return
            elif self.path == "/api/reset":
                self.server.state.detector.reset()
            elif self.path == "/api/test-injection":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 4096:
                        raise ValueError("Expected a small JSON request body")
                    request = json.loads(self.rfile.read(length))
                    self.server.state.configure_injection(request)
                except (ValueError, TypeError, json.JSONDecodeError) as error:
                    self.respond(400, json.dumps({"error":str(error)}).encode())
                    return
            else:
                self.respond(404, b"{}")
                return
        self.respond(200, b'{"ok":true}')


def publish(state):
    while not state.stop.is_set():
        snapshot = state.snapshot()
        data = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
        with state.lock:
            if state.packets:
                try:
                    state.features.write(data.decode("utf-8")+"\n")
                except OSError as error:
                    state.log_error = str(error)
            for client in list(state.clients):
                if client.full():
                    try:
                        client.get_nowait()
                    except queue.Empty:
                        pass
                client.put_nowait(data)
        # Raw packets are still ingested and recorded at their incoming rate.
        # Only the calculated feature snapshot and browser display are limited to 5 Hz.
        time.sleep(0.2)


def consume_ssh_lines(state, lines):
    for line in lines:
        if state.stop.is_set():
            break
        if len(line) > MAX_LINE:
            continue
        try:
            packet = json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
            if not isinstance(packet, dict) or not any(k in packet for k in ("imu", "arms", "pixhawk", "flight_context")):
                continue
            packet.setdefault("source", "pi-ssh")
            state.ingest(packet, "ssh")
            with state.lock:
                state.ssh_status = "receiving JSON over SSH"
        except (ValueError, TypeError, AttributeError):
            # Producer initialization messages are not telemetry.
            continue
    with state.lock:
        state.raw.flush()
        state.audit.flush()


def receive_ssh(state, destination, command, port, identity):
    args = ["ssh", "-T", "-p", str(port), "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=10"]
    if identity:
        args.extend(["-i", identity])
    args.extend([destination, command])
    # Keep the terminal available for normal SSH password and host-key prompts.
    # Do not automatically rerun an unknown remote sensor command after failure.
    try:
        with state.lock:
            state.ssh_status = "connecting / authentication"
        process = subprocess.Popen(args, stdout=subprocess.PIPE, encoding="utf-8", errors="replace")
        state.ssh_process = process
        with state.lock:
            state.ssh_status = "SSH process running; waiting for JSON"
        consume_ssh_lines(state, process.stdout)
        code = process.wait()
        with state.lock:
            state.ssh_status = f"SSH exited ({code}); restart after checking terminal"
    except OSError as error:
        with state.lock:
            state.ssh_status = str(error)
        print(f"SSH error: {error}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--tcp-port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--log-dir", type=Path, default=ROOT / "logs")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--ssh", help="SSH destination: username@host or configured SSH alias")
    parser.add_argument("--ssh-command", help="Existing remote command that prints JSONL")
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--ssh-identity", help="Optional local private-key file path")
    args = parser.parse_args()
    if bool(args.ssh) != bool(args.ssh_command):
        parser.error("Specify both --ssh and --ssh-command")
    if args.ssh and args.ssh.startswith("-"):
        parser.error("SSH destination must not start with '-' ")
    state = State(args.log_dir)
    tcp = None if args.ssh else TCPServer((args.host, args.tcp_port), Receiver)
    web = HTTPServer((args.host, args.web_port), Web)
    web.state = state
    if tcp:
        tcp.state = state
        threading.Thread(target=tcp.serve_forever, daemon=True).start()
    else:
        threading.Thread(target=receive_ssh, args=(state,args.ssh,args.ssh_command,args.ssh_port,args.ssh_identity), daemon=True).start()
    threading.Thread(target=publish, args=(state,), daemon=True).start()
    print(f"ISAS: http://localhost:{args.web_port}/", flush=True)
    print(f"Input: {'SSH '+args.ssh if args.ssh else 'TCP '+str(args.tcp_port)}; raw log: {state.raw_path}", flush=True)
    for ip in sorted(set(socket.gethostbyname_ex(socket.gethostname())[2])):
        print(f"LAN monitor: http://{ip}:{args.web_port}/", flush=True)
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.web_port}/")
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop.set()
        if state.ssh_process and state.ssh_process.poll() is None:
            state.ssh_process.terminate()
        if tcp:
            tcp.shutdown()
            tcp.server_close()
        web.server_close()
        state.raw.close()
        state.audit.close()
        state.features.close()


if __name__ == "__main__":
    main()
