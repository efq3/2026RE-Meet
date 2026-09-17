from w1thermsensor import W1ThermSensor, Sensor, Unit
import time

# 1. 연결된 모든 센서 중에서 DS18B20 센서만 찾아서 리스트로 저장합니다.
sensors = [sensor for sensor in W1ThermSensor.get_available_sensors() if sensor.type == Sensor.DS18B20]

# 센서가 1개 이상 연결되어 있는지 확인합니다.
if len(sensors) > 0:
    print(f"총 {len(sensors)}개의 DS18B20 센서가 성공적으로 감지되었습니다!\n")
    
    # 어떤 센서가 S1~S8로 배정되었는지 고유 ID를 미리 출력해서 보여줍니다.
    for i, sensor in enumerate(sensors):
        print(f"S{i+1} 센서 ID: {sensor.id}")
    print("-" * 60)

    try:
        while True:
            try:
                # 이번 턴에 측정한 온도들을 담을 빈 리스트를 만듭니다.
                temp_results = []
                
                # 8개의 센서를 순서대로 돌면서 온도를 측정합니다.
                for i, sensor in enumerate(sensors):
                    temperature_c = sensor.get_temperature()
                    
                    # S1 : 23.50°C 형식으로 글자를 만들어서 리스트에 넣습니다.
                    temp_results.append(f"S{i+1} : {temperature_c:.2f}°C")
                
                # 리스트에 모인 8개의 결과값을 ' ~ ' 기호로 이어 붙여서 한 줄로 출력합니다.
                final_output = " ~ ".join(temp_results)
                print(final_output)

            except Exception as e:
                # 8개 중 하나라도 통신이 튀면 다음 턴으로 넘깁니다.
                print("데이터 읽기 지연 중... 다음 턴에 재시도합니다.")

            # 모든 센서를 한 번씩 다 읽고 나서 2초 동안 대기합니다.
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")

else:
    print("DS18B20 Sensor not found. (연결된 센서를 찾을 수 없습니다.)")
