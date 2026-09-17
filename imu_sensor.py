import time
import board
import busio
import adafruit_tca9548a
import adafruit_adxl34x

class IMUManager:
    def __init__(self):
        # 1. I2C 및 멀티플렉서 초기화
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.tca = adafruit_tca9548a.TCA9548A(self.i2c)
        
        # 2. 오프셋 설정
        self.offsets = {
            0: (0.7, 0.5, -0.7),
            1: (0.2, 0.4, -0.2),
            2: (0.6, 0.4, -0.6),
            3: (0.6, 0.2, 0.7)
        }
        
        # 3. 센서 초기화 및 매핑
        target_channels = [0, 1, 2, 3]
        self.sensors = {}
        
        for ch in target_channels:
            try:
                sensor = adafruit_adxl34x.ADXL345(self.tca[ch])
                self.sensors[ch] = sensor
            except Exception:
                pass
                
        time.sleep(0.01)

    def get_data(self):
        """현재 센서의 데이터를 읽어와서 딕셔너리 형태로 반환합니다."""
        if not self.sensors:
            return {"error": "연결된 센서가 하나도 없습니다."}
            
        sensor_data = {}
        for ch, sensor in self.sensors.items():
            channel_name = f"CH{ch}"
            try:
                raw_x, raw_y, raw_z = sensor.acceleration
                off_x, off_y, off_z = self.offsets.get(ch, (0.0, 0.0, 0.0))
                
                cal_x = raw_x - off_x
                cal_y = raw_y - off_y
                cal_z = raw_z - off_z
                
                # 보정된 데이터를 딕셔너리에 저장
                sensor_data[channel_name] = {
                    "X": round(cal_x, 1),
                    "Y": round(cal_y, 1),
                    "Z": round(cal_z, 1)
                }
            except OSError:
                sensor_data[channel_name] = "error"
                
        return sensor_data