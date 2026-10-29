import time
import json
import math
import threading
from pymavlink import mavutil

px4_data = {
    "flight_mode": "UNKNOWN",
    "landed_state": "UNKNOWN",
    "throttle_pct": 0,
    "attitude": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    "battery": {"voltage": 0.0, "percent": 0},
    "vibration": {"x": 0.0, "y": 0.0, "z": 0.0}
}

def update_pixhawk_data(master):
    """
    백그라운드에서 끊임없이 MAVLink 메시지를 수신하여 전역 변수를 업데이트하는 스레드 함수
    """
    global px4_data
    while True:
        msg = master.recv_match(blocking=False)
        
        if msg:
            msg_type = msg.get_type()
            
            if msg_type == 'HEARTBEAT':
                px4_data["flight_mode"] = mavutil.mode_string_v10(msg)
            elif msg_type == 'EXTENDED_SYS_STATE':
                if msg.landed_state == 1:
                    px4_data["landed_state"] = "LANDED"
                elif msg.landed_state == 2:
                    px4_data["landed_state"] = "IN_AIR"
            elif msg_type == 'VFR_HUD':
                px4_data["throttle_pct"] = msg.throttle
            elif msg_type == 'ATTITUDE':
                px4_data["attitude"]["roll"] = round(math.degrees(msg.roll), 2)
                px4_data["attitude"]["pitch"] = round(math.degrees(msg.pitch), 2)
                px4_data["attitude"]["yaw"] = round(math.degrees(msg.yaw), 2)
            elif msg_type == 'SYS_STATUS':
                px4_data["battery"]["voltage"] = round(msg.voltage_battery / 1000.0, 2)
                px4_data["battery"]["percent"] = msg.battery_remaining
            elif msg_type == 'VIBRATION':
                px4_data["vibration"]["x"] = round(msg.vibration_x, 3)
                px4_data["vibration"]["y"] = round(msg.vibration_y, 3)
                px4_data["vibration"]["z"] = round(msg.vibration_z, 3)
        else:
            # 수신된 메시지가 없을 때 CPU 과부하를 막기 위해 아주 짧게 대기
            time.sleep(0.001)

def main():
    CONNECTION_STRING = '/dev/serial0' 
    BAUD_RATE = 57600

    print(f"{CONNECTION_STRING} 포트로 픽스호크 연결 대기 중...")
    master = mavutil.mavlink_connection(CONNECTION_STRING, baud=BAUD_RATE)
    master.wait_heartbeat()
    print("픽스호크와 정상적으로 연결되었습니다!")

    master.mav.request_data_stream_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,
        10,
        1
    )

    # 픽스호크 데이터(백그라운드 스레드 시작)
    pixhawk_thread = threading.Thread(target=update_pixhawk_data, args=(master,), daemon=True)
    pixhawk_thread.start()

    log_filename = f"flight_log_{int(time.time())}.txt"
    print(f"데이터 {log_filename}에 저장...")

    try:
        with open(log_filename, 'a', encoding='utf-8') as f:
            while True:
                current_time = time.time()
                output_data = {
                    "timestamp": round(current_time, 3),
                    "pixhawk": px4_data
                }
                
                json_str = json.dumps(output_data, sort_keys=True)
                print(json_str)
                
                f.write(json_str + '\n')
                f.flush()
                
                time.sleep(0.001)

    except KeyboardInterrupt:
        print(f"\n데이터 수집을 종료합니다. 저장된 파일: {log_filename}")

if __name__ == "__main__":
    main()