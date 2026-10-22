import time
import json
import threading
from imu_sensor import IMUManager
from temp_sensor import TempSensorManager

# 전역 변수: 온도 스레드가 읽어온 최신 값을 저장해두는 공간
latest_temp_data = {"status": "온도 초기화 중..."}

def update_temperature(temp_manager):
    global latest_temp_data
    while True:
        # 온도를 읽어오고(약 1~3초 소요) 전역 변수를 갱신함
        data = temp_manager.get_data()
        latest_temp_data = data
        
        # 너무 잦은 호출로 인한 1-Wire 버스 부하를 막기 위해 약간 대기
        time.sleep(1)

def main():
    print("센서 매니저 초기화 중...")

    print("Temp sensor reset")
    temp = TempSensorManager()
    print("Suc Temp sensor reset")

    print("IMU 초기화 시도...")
    imu = IMUManager()
    print("IMU 초기화 완료")
    
    # 1. 온도 센서를 읽는 백그라운드 스레드 시작
    temp_thread = threading.Thread(target=update_temperature, args=(temp,), daemon=True)
    temp_thread.start()
    
    # 잠시 대기하여 온도 센서가 첫 번째 값을 읽어올 시간을 줌
    time.sleep(1.5)
    
    # 저장할 파일 이름 설정 (실행할 때마다 덮어쓰지 않도록 파일명에 시간 포함)
    log_filename = f"sensor_log_{int(time.time())}.txt"
    print(f"데이터를 {log_filename} 파일에 저장하기 시작합니다...")
    
    try:
        # 'a' 모드(Append)로 파일을 엽니다. 파일이 없으면 새로 생성합니다.
        with open(log_filename, "a", encoding="utf-8") as f:
            while True:
                imu_data = imu.get_data()
                current_timestamp = time.time() 
                
                combined_data = {
                    "timestamp": round(current_timestamp, 3),
                    "imu": imu_data,
                    "temperature": latest_temp_data
                }
                
                # JSON으로 변환
                json_output = json.dumps(combined_data, sort_keys=True)
                
                # 1) 화면에 출력 (터미널에서 상태를 보기 위함)
                print(json_output)
                
                # 2) 파일에 기록 (끝에 줄바꿈 \n 추가)
                f.write(json_output + "\n")
                
                # 3) 버퍼를 비워 실제 파일에 즉시 쓰기 (전원이 끊겨도 데이터 유실 방지)
                f.flush()
                
                time.sleep(0.001) 
                
    except KeyboardInterrupt:
        print(f"\n데이터 수집을 종료합니다. 저장된 파일: {log_filename}")

if __name__ == "__main__":
    main()
