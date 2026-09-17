import time
import board
import busio
import adafruit_tca9548a
import adafruit_adxl34x

# 캘리브레이션을 진행할 MUX 채널 번호 설정 (0, 1, 2, 3 중 하나)
TARGET_CH = 0

def main():
    # I2C 및 멀티플렉서 초기화
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = adafruit_tca9548a.TCA9548A(i2c)
    
    try:
        sensor = adafruit_adxl34x.ADXL345(tca[TARGET_CH])
    except Exception as e:
        print(f"CH{TARGET_CH} 센서를 찾을 수 없습니다. 배선을 확인하세요: {e}")
        return

    print(f"=== CH{TARGET_CH} ADXL345 캘리브레이션 시작 ===")
    print("Adafruit 라이브러리는 중력가속도(m/s^2) 단위로 출력됩니다.\n")
    measurements = {}
    
    orientations = [
        ('Z', '+1g (센서를 똑바로 눕힘)'),
        ('Z', '-1g (센서를 뒤집음)'),
        ('X', '+1g (X축 화살표가 바닥을 향함)'),
        ('X', '-1g (X축 화살표가 하늘을 향함)'),
        ('Y', '+1g (Y축 화살표가 바닥을 향함)'),
        ('Y', '-1g (Y축 화살표가 하늘을 향함)')
    ]

    for axis, desc in orientations:
        input(f"[{axis}축 측정] {desc} 상태로 두고 Enter를 누르세요...")
        print("데이터 수집 중...")
        
        # 100번 측정 후 평균값 산출
        x_sum, y_sum, z_sum = 0, 0, 0
        for _ in range(100):
            x, y, z = sensor.acceleration
            x_sum += x
            y_sum += y
            z_sum += z
            time.sleep(0.01)
            
        avg_x = x_sum / 100
        avg_y = y_sum / 100
        avg_z = z_sum / 100
        
        # 주축 데이터 저장
        if axis == 'X' and '+1g' in desc: measurements['X_MAX'] = avg_x
        elif axis == 'X' and '-1g' in desc: measurements['X_MIN'] = avg_x
        elif axis == 'Y' and '+1g' in desc: measurements['Y_MAX'] = avg_y
        elif axis == 'Y' and '-1g' in desc: measurements['Y_MIN'] = avg_y
        elif axis == 'Z' and '+1g' in desc: measurements['Z_MAX'] = avg_z
        elif axis == 'Z' and '-1g' in desc: measurements['Z_MIN'] = avg_z
        
        print(f"완료! 측정값: X={avg_x:.2f}, Y={avg_y:.2f}, Z={avg_z:.2f}\n")

    # 오프셋 계산: (Max + Min) / 2
    offset_x = (measurements['X_MAX'] + measurements['X_MIN']) / 2.0
    offset_y = (measurements['Y_MAX'] + measurements['Y_MIN']) / 2.0
    offset_z = (measurements['Z_MAX'] + measurements['Z_MIN']) / 2.0

    print(f"=== CH{TARGET_CH} 캘리브레이션 완료 ===")
    print(f"계산된 오프셋 값: ({offset_x:.3f}, {offset_y:.3f}, {offset_z:.3f})")
    print(f"\n작성해주신 기존 클래스의 self.offsets 딕셔너리에서 {TARGET_CH}번 키의 값을 위 결과로 수정하시면 됩니다.")

if __name__ == '__main__':
    main()