from w1thermsensor import W1ThermSensor, Sensor
import time

class TempSensorManager:
    def __init__(self):
        # 1. 센서 ID 매핑
        self.sensor_map = {
            "0625659202d1": "S1",
            "40ba008750ff": "S2",
            "0625659b7f3e": "S3",
            "062565416895": "S4",
        }
        
        # 2. 연결된 DS18B20 센서 검색 및 저장
        self.sensors = [
            sensor for sensor in W1ThermSensor.get_available_sensors() 
            if sensor.type == Sensor.DS18B20
        ]

    def get_data(self):
        """현재 온도 센서들의 데이터를 읽어와서 딕셔너리 형태로 반환합니다."""
        if not self.sensors:
            return {"error": "DS18B20 센서를 찾을 수 없습니다."}

        sensor_data = {}
        
        for sensor in self.sensors:
            sensor_name = self.sensor_map.get(sensor.id, f"unknown({sensor.id})")
            temperature_c = None
            
            # 읽기 실패 시 1회 재시도 (총 2회)
            for attempt in range(2):
                try:
                    temperature_c = sensor.get_temperature()
                    break
                except Exception:
                    time.sleep(1)
            
            # 3. 측정된 값을 딕셔너리에 저장
            if temperature_c is not None:
                sensor_data[sensor_name] = round(temperature_c, 1)
            else:
                sensor_data[sensor_name] = "error"
                
        return sensor_data