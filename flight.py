import time
import json
import math
from pymavlink import mavutil

# 1. 픽스호크 연결 설정
# USB로 연결했을 경우 보통 '/dev/ttyACM0' 입니다.
# 라즈베리파이 GPIO 핀(UART)으로 연결했다면 '/dev/serial0' 또는 '/dev/ttyAMA0'를 사용하세요.
CONNECTION_STRING = '/dev/serial0' 
BAUD_RATE = 57600

print(f"{CONNECTION_STRING} 포트로 픽스호크 연결 대기 중...")
# 픽스호크와 연결 시도
master = mavutil.mavlink_connection(CONNECTION_STRING, baud=BAUD_RATE)

# HEARTBEAT 메시지가 올 때까지 대기 (연결 확인용)
master.wait_heartbeat()
print("픽스호크와 정상적으로 연결되었습니다!")

# 2. 수신한 데이터를 저장해둘 딕셔너리
px4_data = {
    "flight_mode": "UNKNOWN",
    "landed_state": "UNKNOWN",
    "throttle_pct": 0,
    "attitude": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    "battery": {"voltage": 0.0, "percent": 0},
    "vibration": {"x": 0.0, "y": 0.0, "z": 0.0}
}

last_print_time = time.time()

try:
    while True:
        # 3. 픽스호크로부터 쏟아지는 MAVLink 메시지 수신 (blocking=False로 멈춤 방지)
        msg = master.recv_match(blocking=False)
        
        if msg:
            msg_type = msg.get_type()
            
            # (1) 비행 모드 (HEARTBEAT)
            if msg_type == 'HEARTBEAT':
                px4_data["flight_mode"] = mavutil.mode_string_v10(msg)
                
            # (2) 이착륙 상태 (EXTENDED_SYS_STATE)
            elif msg_type == 'EXTENDED_SYS_STATE':
                if msg.landed_state == 1:
                    px4_data["landed_state"] = "LANDED"
                elif msg.landed_state == 2:
                    px4_data["landed_state"] = "IN_AIR"
                    
            # (3) 스로틀 오더 퍼센트 (VFR_HUD)
            elif msg_type == 'VFR_HUD':
                px4_data["throttle_pct"] = msg.throttle
                
            # (4) Roll, Pitch, Yaw (ATTITUDE) - 라디안으로 오기 때문에 디그리로 변환
            elif msg_type == 'ATTITUDE':
                px4_data["attitude"]["roll"] = round(math.degrees(msg.roll), 2)
                px4_data["attitude"]["pitch"] = round(math.degrees(msg.pitch), 2)
                px4_data["attitude"]["yaw"] = round(math.degrees(msg.yaw), 2)
                
            # (5) 배터리 및 전압 (SYS_STATUS) - mV로 오기 때문에 V로 변환
            elif msg_type == 'SYS_STATUS':
                px4_data["battery"]["voltage"] = round(msg.voltage_battery / 1000.0, 2)
                px4_data["battery"]["percent"] = msg.battery_remaining
                
            # (6) 픽스호크 내부 진동 원시데이터 (VIBRATION)
            elif msg_type == 'VIBRATION':
                px4_data["vibration"]["x"] = round(msg.vibration_x, 3)
                px4_data["vibration"]["y"] = round(msg.vibration_y, 3)
                px4_data["vibration"]["z"] = round(msg.vibration_z, 3)

        # 4. 0.5초마다 한 번씩 최신 데이터를 JSON으로 출력
        current_time = time.time()
        if current_time - last_print_time >= 0.5:
            # 타임스탬프를 추가하여 출력
            output_data = {
                "timestamp": round(current_time, 3),
                "pixhawk": px4_data
            }
            print(json.dumps(output_data, sort_keys=True))
            last_print_time = current_time

except KeyboardInterrupt:
    print("\n픽스호크 데이터 수집을 종료합니다.")