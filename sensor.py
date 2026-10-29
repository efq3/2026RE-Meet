import time
import json
import threading
from imu_sensor import IMUManager
from temp_sensor import TempSensorManager

latest_temp_data = {"status": "온도 초기화 중..."}

def update_temperature(temp_manager):
    global latest_temp_data
    while True:
        data = temp_manager.get_data()
        latest_temp_data = data
        time.sleep(1)

def main():
    print("센서 매니저 초기화 중...")

    print("Temp sensor reset")
    temp = TempSensorManager()
    print("Suc Temp sensor reset")

    print("IMU 초기화 시도...")
    imu = IMUManager()
    print("IMU 초기화 완료")
    
    # 1. 온도 센서(백그라운드 스레드 시작)
    temp_thread = threading.Thread(target=update_temperature, args=(temp,), daemon=True)
    temp_thread.start()
    
    time.sleep(1.5)  # 온도 센서 값 대기 시간
    
    log_filename = f"sensor_log_{int(time.time())}.txt"
    print(f"데이터 {log_filename}에 저장...")
    
    try:
        with open(log_filename, "a", encoding="utf-8") as f:
            while True:
                imu_data = imu.get_data()

                current_timestamp = time.time() 
                combined_data = {
                    "timestamp": round(current_timestamp, 3),
                    "imu": imu_data,
                    "temperature": latest_temp_data
                }
                
                json_output = json.dumps(combined_data, sort_keys=True)
                print(json_output)

                f.write(json_output + "\n")
                f.flush()
                
                time.sleep(0.001) 
                
    except KeyboardInterrupt:
        print(f"\n데이터 수집을 종료합니다. 저장된 파일: {log_filename}")

if __name__ == "__main__":
    main()
