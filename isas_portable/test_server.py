import json
import io
import math
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from server import HTTPServer, Receiver, State, TCPServer, Web, consume_ssh_lines


class ServerTests(unittest.TestCase):
    def test_four_arm_temperature_and_rms_without_flight_context(self):
        with tempfile.TemporaryDirectory() as temp:
            state = State(Path(temp))
            try:
                for index in range(251):
                    t = index / 125
                    packet = {
                        "timestamp": 1000 + t,
                        "imu": {
                            f"CH{i}": {
                                "X": math.sqrt(2) * (i + 1) * math.sin(2 * math.pi * 5 * t),
                                "Y": i + 2,
                                "Z": 9.8,
                            }
                            for i in range(4)
                        },
                        "temperature": {f"S{i + 1}": 25 + i * 0.5 for i in range(4)},
                    }
                    state.ingest(packet, "test")
                result = state.snapshot()
                expected_rms = [1, 3, 2, 4]
                for i, arm in enumerate(result["arms"]):
                    self.assertAlmostEqual(arm["rms"], expected_rms[i], delta=0.02)
                    self.assertEqual(arm["temperature"], 25 + i * 0.5)
                    self.assertAlmostEqual(arm["hz"], 125)
                    self.assertEqual(arm["status"], "context_missing")
                self.assertFalse(result["baseline_set"])
                self.assertFalse(result["flight_eligible"])
                state.raw.flush()
                raw_packet = json.loads(state.raw_path.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(raw_packet["imu"], packet["imu"])
            finally:
                state.raw.close(); state.audit.close(); state.features.close()

    def test_simulation_vibration_injection_preserves_raw_packet(self):
        with tempfile.TemporaryDirectory() as temp:
            state=State(Path(temp))
            try:
                state.configure_injection({"enabled":True,"rms_mps2":[0,0,1,0],"frequency_hz":10})
                for index in range(250):
                    packet={"timestamp":1000+index/125,"source":"px4-gazebo-sitl","simulation":True,
                            "imu":{f"CH{i}":{"X":0,"Y":0,"Z":9.8} for i in range(4)},
                            "flight_context":{"armed":True,"attitude_deg":{"roll":0,"pitch":0},
                                              "angular_velocity_rad_s":{"x":0,"y":0,"z":0}}}
                    state.ingest(packet,"test")
                self.assertAlmostEqual(state.detector.samples[0][-1][1][2],9.8)
                self.assertNotAlmostEqual(state.detector.samples[2][-1][1][2],9.8)
                state.raw.flush()
                recorded=json.loads(state.raw_path.read_text().splitlines()[-1])
                self.assertEqual(recorded["imu"]["CH2"]["Z"],9.8)
                self.assertTrue(state.snapshot()["test_injection"]["enabled"])
            finally:
                state.raw.close();state.audit.close();state.features.close()

    def test_ssh_stdout_initialization_and_json_are_separated(self):
        with tempfile.TemporaryDirectory() as temp:
            state=State(Path(temp))
            try:
                lines=io.StringIO('Initializing sensors...\n{"timestamp":1000,"imu":{"CH0":{"X":0,"Y":0,"Z":9.8}},"temperature":{"status":"initializing"}}\nnot JSON\n')
                consume_ssh_lines(state,lines)
                self.assertEqual(state.packets,1)
                self.assertEqual(state.ssh_status,"receiving JSON over SSH")
                self.assertEqual(state.detector.samples[0][0][1],[0,0,9.8])
                self.assertIsNone(state.detector.temps[0])
                self.assertEqual(json.loads(state.raw_path.read_text())["source"],"pi-ssh")
            finally:
                state.raw.close();state.audit.close();state.features.close()

    def test_tcp_fragmentation_recording_status_and_download(self):
        with tempfile.TemporaryDirectory() as temp:
            state=State(Path(temp))
            tcp=TCPServer(("127.0.0.1",0),Receiver)
            http=HTTPServer(("127.0.0.1",0),Web)
            tcp.state=http.state=state
            threading.Thread(target=tcp.serve_forever,daemon=True).start()
            threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f"http://127.0.0.1:{http.server_port}"
            try:
                with socket.create_connection(tcp.server_address) as client:
                    client.sendall(b'not-json\n{"timestamp":1000,"imu":')
                    client.sendall(b'{"CH0":{"X":0,"Y":0,"Z":9.8}},"temperature":{"S1":25}}\n')
                    deadline=time.monotonic()+3
                    while state.packets<1 and time.monotonic()<deadline:
                        time.sleep(.01)
                with urllib.request.urlopen(base+"/api/status") as response:
                    status=json.load(response)
                self.assertEqual(status["packets"],1)
                self.assertEqual(status["invalid_lines"],1)
                self.assertEqual(status["arms"][0]["temperature"],25)
                self.assertIsNone(status["arms"][1]["temperature"])
                with urllib.request.urlopen(base+"/api/log") as response:
                    log=response.read().decode()
                self.assertEqual(json.loads(log)["timestamp"],1000)
                with urllib.request.urlopen(base+"/api/logs.zip") as response:
                    archive_bytes=response.read()
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    names=set(archive.namelist())
                    self.assertIn(state.raw_path.name,names)
                    self.assertIn(state.audit_path.name,names)
                    self.assertIn(state.feature_path.name,names)
                    self.assertIn(state.config_path.name,names)
                    archived=json.loads(archive.read(state.raw_path.name).decode())
                    self.assertEqual(archived["timestamp"],1000)
                with urllib.request.urlopen(base) as response:
                    self.assertIn(b"ISAS",response.read())
                request=urllib.request.Request(base+"/api/reset",data=b"",headers={"Origin":"http://other-site.invalid"})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,403)
                payload=json.dumps({"enabled":True,"rms_mps2":[0,0,0.8,0],"frequency_hz":30}).encode()
                request=urllib.request.Request(base+"/api/test-injection",data=payload,
                    headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)["ok"])
                with urllib.request.urlopen(base+"/api/status") as response:
                    self.assertEqual(json.load(response)["test_injection"]["rms_mps2"][2],0.8)
            finally:
                tcp.shutdown();http.shutdown()
                tcp.server_close();http.server_close()
                state.raw.close();state.audit.close();state.features.close()


if __name__=="__main__":
    unittest.main()
