import time
import json
import threading
from collections import deque

import matplotlib
matplotlib.use('TkAgg') # VNC 환경을 위한 백엔드 설정
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# 분리해둔 모듈들
from imu_sensor import IMUManager
from temp_sensor import TempSensorManager

# 전역 변수: 온도 스레드가 갱신할 최신 데이터
latest_temp_data = {"status": "온도 초기화 중..."}

# 그래프를 위한 데이터 버퍼 (최근 50개 데이터만 유지)
MAX_POINTS = 50
time_history = deque(maxlen=MAX_POINTS)

# IMU CH0 데이터 버퍼
ch0_x = deque(maxlen=MAX_POINTS)
ch0_y = deque(maxlen=MAX_POINTS)
ch0_z = deque(maxlen=MAX_POINTS)

# 온도 센서 4개 데이터 버퍼 모두 추가
temp_s1 = deque(maxlen=MAX_POINTS)
temp_s2 = deque(maxlen=MAX_POINTS)
temp_s3 = deque(maxlen=MAX_POINTS)
temp_s4 = deque(maxlen=MAX_POINTS)

def update_temperature(temp_manager):
    """백그라운드에서 온도만 계속 갱신하는 스레드"""
    global latest_temp_data
    while True:
        latest_temp_data = temp_manager.get_data()
        time.sleep(1)

def main():
    print("센서 초기화 중... 잠시만 기다려주세요.")
    imu = IMUManager()
    temp = TempSensorManager()
    
    # 온도 센서 백그라운드 스레드 시작
    temp_thread = threading.Thread(target=update_temperature, args=(temp,), daemon=True)
    temp_thread.start()
    time.sleep(1.5)
    
    # ------------------------------------------------
    # 그래프(Matplotlib) 창 기본 세팅
    # ------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    fig.canvas.manager.set_window_title('Real-time Sensor Data')
    
    # 윗부분: IMU 그래프 선 세팅
    line_x, = ax1.plot([], [], label='CH0 X', color='r', linewidth=2)
    line_y, = ax1.plot([], [], label='CH0 Y', color='g', linewidth=2)
    line_z, = ax1.plot([], [], label='CH0 Z', color='b', linewidth=2)
    ax1.set_title("IMU CH0 Acceleration")
    ax1.set_ylabel("Accel (m/s^2)")
    ax1.legend(loc='upper right')
    ax1.grid(True)
    
    # 아랫부분: 온도 그래프 선 4개 모두 세팅
    line_t1, = ax2.plot([], [], label='S1 Temp', color='orange', linewidth=2, marker='o')
    line_t2, = ax2.plot([], [], label='S2 Temp', color='cyan', linewidth=2, marker='o')
    line_t3, = ax2.plot([], [], label='S3 Temp', color='magenta', linewidth=2, marker='o')
    line_t4, = ax2.plot([], [], label='S4 Temp', color='black', linewidth=2, marker='o')
    ax2.set_title("Temperature (DS18B20)")
    ax2.set_ylabel("Temp (°C)")
    ax2.legend(loc='upper right')
    ax2.grid(True)
    
    start_time = time.time()
    
    # ------------------------------------------------
    # 실시간 업데이트 로직
    # ------------------------------------------------
    def animate(frame):
        current_time = time.time()
        elapsed = current_time - start_time
        
        # 1. IMU 데이터 수집 및 병합
        imu_data = imu.get_data()
        combined_data = {
            "timestamp": round(current_time, 3),
            "imu": imu_data,
            "temperature": latest_temp_data
        }
        
        # 2. 터미널에 JSON 출력
        print(json.dumps(combined_data, sort_keys=True))
        
        # 3. 시간값 버퍼에 추가
        time_history.append(elapsed)
        
        # 4. IMU CH0 데이터 버퍼에 추가
        ch0 = imu_data.get("CH0", {})
        if isinstance(ch0, dict) and "X" in ch0:
            ch0_x.append(ch0["X"])
            ch0_y.append(ch0["Y"])
            ch0_z.append(ch0["Z"])
        else:
            ch0_x.append(0); ch0_y.append(0); ch0_z.append(0)
            
        # 5. 온도 S1~S4 데이터 버퍼에 모두 추가
        t_data = latest_temp_data
        if isinstance(t_data, dict):
            s1_val = t_data.get("S1", 0)
            s2_val = t_data.get("S2", 0)
            s3_val = t_data.get("S3", 0)
            s4_val = t_data.get("S4", 0)
            
            temp_s1.append(s1_val if isinstance(s1_val, (int, float)) else 0)
            temp_s2.append(s2_val if isinstance(s2_val, (int, float)) else 0)
            temp_s3.append(s3_val if isinstance(s3_val, (int, float)) else 0)
            temp_s4.append(s4_val if isinstance(s4_val, (int, float)) else 0)
        
        # 6. X축(시간) 스크롤 이동
        min_x = max(0, elapsed - 5)
        max_x = elapsed + 0.5
        ax1.set_xlim(min_x, max_x)
        ax2.set_xlim(min_x, max_x)
        
        # 7. Y축 범위 세팅
        ax1.set_ylim(-15, 15) 
        ax2.set_ylim(20, 50)  
        
        # 8. 4개의 온도 선에 새로운 데이터 적용
        line_x.set_data(time_history, ch0_x)
        line_y.set_data(time_history, ch0_y)
        line_z.set_data(time_history, ch0_z)
        
        line_t1.set_data(time_history, temp_s1)
        line_t2.set_data(time_history, temp_s2)
        line_t3.set_data(time_history, temp_s3)
        line_t4.set_data(time_history, temp_s4)
        
        return line_x, line_y, line_z, line_t1, line_t2, line_t3, line_t4

    # 애니메이션 실행
    ani = animation.FuncAnimation(fig, animate, interval=100, cache_frame_data=False)
    
    plt.tight_layout()
    plt.show() 

if __name__ == "__main__":
    main()