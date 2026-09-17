import time
import json
import threading
from imu_sensor import IMUManager
from temp_sensor import TempSensorManager

# 전역 변수: 온도 스레드가 읽어온 최신 값을 저장해두는 공간
latest_temp_data = {"status": "온도 초기화 중..."}

def update_temperature(temp_manager):
    """
    백그라운드에서 계속 실행되며 온도 데이터만 전담해서 업데이트하는 함수 (느림)
    """
    global latest_temp_data
    while True:
        # 온도를 읽어오고(약 1~3초 소요) 전역 변수를 갱신함
        data = temp_manager.get_data()
        latest_temp_data = data
        
        # 너무 잦은 호출로 인한 1-Wire 버스 부하를 막기 위해 약간 대기
        time.sleep(1)

def main():
    print("센서 매니저 초기화 중...")
    imu = IMUManager()
    temp = TempSensorManager()
    
    # 1. 온도 센서를 읽는 백그라운드 스레드 시작
    # daemon=True로 설정하면 메인 프로그램(IMU 루프) 종료 시 같이 안전하게 죽습니다.
    temp_thread = threading.Thread(target=update_temperature, args=(temp,), daemon=True)
    temp_thread.start()
    
    # 잠시 대기하여 온도 센서가 첫 번째 값을 읽어올 시간을 줌
    time.sleep(1.5)
    
    try:
        while True:
            # 2. 메인 루프 (IMU 기준, 매우 빠름)
            imu_data = imu.get_data()
            
            # 현재 시간을 타임스탬프로 사용 (초 단위 실수)
            current_timestamp = time.time() 
            
            # 3. 데이터 합치기 (최신 IMU 데이터 + 스레드가 갱신해둔 최신 온도 데이터)
            combined_data = {
                "timestamp": round(current_timestamp, 3), # 소수점 3자리(밀리초)까지 표현
                "imu": imu_data,
                "temperature": latest_temp_data
            }
            
            # 4. JSON으로 출력
            json_output = json.dumps(combined_data, sort_keys=True)
            print(json_output)
            
            # IMU 업데이트 주기 설정 (예: 0.1초 = 10Hz)
            # 제어 주기에 맞게 이 값을 조절하시면 됩니다.
            time.sleep(0.05) 
            
    except KeyboardInterrupt:
        print("\n데이터 수집 루프를 종료합니다.")

if __name__ == "__main__":
    main()