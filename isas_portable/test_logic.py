import copy
import json
import math
import unittest
from pathlib import Path

from logic import Detector


class LogicTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(Path(__file__).with_name("config.json").read_text())
        self.detector = Detector(self.config)

    def packet(self, t, fault=False):
        return {"timestamp":1000+t,"imu":{f"CH{i}":{"X":(1.4 if fault and i==2 else 0.03)*math.sin(2*math.pi*7*t),"Y":-1.5,"Z":9.8} for i in range(4)},
                "temperature":{f"S{i+1}":25+(8 if fault and i==2 else 0) for i in range(4)},
                "flight_context":{"armed":True,"attitude_deg":{"roll":0,"pitch":0},"angular_velocity_rad_s":{"x":0,"y":0,"z":0}}}

    def feed(self, start, end, fault=False):
        result = None
        for k in range(round(start*50),round(end*50)):
            t=k/50
            self.detector.ingest(self.packet(t,fault),t)
            result=self.detector.snapshot(t)
        return result

    def test_constant_offset_is_not_vibration(self):
        for k in range(110):
            p=self.packet(k/50)
            for i,a in enumerate(p["imu"].values()):
                a.update(X=3+i,Y=-1.5,Z=9.8+i)
            self.detector.ingest(p,k/50)
        result=self.detector.snapshot(2.18)
        self.assertTrue(all(a["ready"] for a in result["arms"]))
        self.assertTrue(all(a["rms"]<1e-10 for a in result["arms"]))

    def test_persistent_same_arm_compound(self):
        self.feed(0,3)
        self.detector.set_baseline(2.98)
        early=self.feed(3,4,True)
        self.assertFalse(early["arms"][2]["vibration_candidate"])
        result=self.feed(4,9,True)
        self.assertEqual(result["arms"][2]["status"],"compound_candidate")
        self.assertFalse(result["arms"][0]["vibration_candidate"])

    def test_context_missing_blocks_vibration_but_keeps_temperature(self):
        for k in range(400):
            p=self.packet(k/50,True)
            p.pop("flight_context")
            self.detector.ingest(p,k/50)
            result=self.detector.snapshot(k/50)
        self.assertFalse(result["flight_eligible"])
        self.assertFalse(result["arms"][2]["vibration_candidate"])

    def test_stale_clears_candidate(self):
        self.feed(0,6,True)
        result=self.detector.snapshot(10)
        self.assertTrue(all(a["status"]=="data_missing" for a in result["arms"]))
        self.assertTrue(all(not a["vibration_candidate"] for a in result["arms"]))

    def test_temperature_initialization_does_not_drop_imu(self):
        for k in range(120):
            p=self.packet(k/50)
            p["temperature"]={"status":"initializing"}
            p["imu"]["CH1"]="error"
            self.detector.ingest(p,k/50)
        result=self.detector.snapshot(2.38)
        self.assertTrue(result["arms"][0]["ready"])
        self.assertIsNone(result["arms"][0]["temperature"])
        self.assertFalse(result["arms"][1]["ready"])
        with self.assertRaises(ValueError):
            self.detector.set_baseline(2.38)

    def test_duplicate_and_reverse_timestamps_not_counted(self):
        p=self.packet(0)
        self.detector.ingest(p,0)
        self.detector.ingest(p,0.1)
        self.detector.ingest(self.packet(-1),0.2)
        self.assertEqual(len(self.detector.samples[0]),1)
        self.assertEqual(self.detector.timestamp_errors,8)

    def test_low_rate_not_called_high_bandwidth(self):
        for k in range(50):
            self.detector.ingest(self.packet(k/10),k/10)
        result=self.detector.snapshot(4.9)
        self.assertAlmostEqual(result["arms"][0]["hz"],10)
        self.assertFalse(result["arms"][0]["bandwidth_sufficient"])

    def test_maneuver_clears_vibration(self):
        self.feed(0,7,True)
        p=self.packet(7,True)
        p["flight_context"]["angular_velocity_rad_s"]["x"]=1
        self.detector.ingest(p,7)
        result=self.detector.snapshot(7)
        self.assertEqual(result["arms"][2]["status"],"maneuver")
        self.assertFalse(result["arms"][2]["vibration_candidate"])

    def test_strict_numeric_and_stale_temperature_timestamp(self):
        p=self.packet(0)
        p["imu"]["CH0"]["X"]=None
        p["temperature"]["S1"]=True
        p["temperature_timestamp"]=1
        self.detector.ingest(p,0)
        result=self.detector.snapshot(0)
        self.assertIsNone(result["arms"][0]["temperature"])
        self.assertIsNone(result["arms"][1]["temperature"])

    def test_multi_source_does_not_mix_sensor_windows(self):
        a=self.packet(0);a["source"]="first"
        b=self.packet(0.1);b["source"]="second"
        b["flight_context"]["armed"]=False
        self.detector.ingest(a,0)
        self.detector.ingest(b,0.1)
        self.assertEqual(len(self.detector.samples[0]),1)
        self.assertEqual(self.detector.stream_conflicts,1)
        self.assertTrue(self.detector.context["armed"])
        self.assertEqual(self.detector.context_source,"first")


if __name__ == "__main__":
    unittest.main()
