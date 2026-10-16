import time
import board
import busio
import adafruit_tca9548a
import adafruit_adxl34x

def main():
    # I2C 및 멀티플렉서 초기화
    i2c = busio.I2C(board.SCL, board.SDA)
    tca = adafruit_tca9548a.TCA9548A(i2c)

    print("=== 멀티플렉서 채널 0~3 스캔 중 ===")
    active_sensors = {}
    
    # 1. 채널 0~3 센서 연결 확인
    for ch in range(4):
        try:
            sensor = adafruit_adxl34x.ADXL345(tca[ch])
            active_sensors[ch] = sensor
            print(f"CH{ch}: 센서 인식 성공")
        except Exception as e:
            print(f"CH{ch}: 센서 인식 불가 - 연결을 확인하세요. ({e})")
            
    if not active_sensors:
        print("\n인식된 센서가 하나도 없습니다. 스크립트를 종료합니다.")
        return

    print("\n=== 다중 채널 ADXL345 캘리브레이션 시작 ===")
    print("Adafruit 라이브러리는 m/s^2 단위로 데이터를 출력합니다.\n")
    
    # 채널별 측정값을 저장할 딕셔너리
    measurements = {ch: {} for ch in active_sensors.keys()}

    orientations = [
        ('Z', '+1g (센서를 평평하게 바닥에 놓기)'),
        ('Z', '-1g (센서를 완전히 뒤집어서 놓기)'),
        ('X', '+1g (X축 화살표가 땅을 향하게 수직으로 세우기)'),
        ('X', '-1g (X축 화살표가 하늘을 향하게 수직으로 세우기)'),
        ('Y', '+1g (Y축 화살표가 땅을 향하게 옆으로 세우기)'),
        ('Y', '-1g (Y축 화살표가 하늘을 향하게 옆으로 세우기)')
    ]

    # 2. 각 방향별로 데이터 동시 수집
    for axis, desc in orientations:
        input(f"[{axis}축 측정] 센서 모듈들을 '{desc}' 방향으로 위치시키고 Enter를 누르세요...")
        print("데이터 수집 중...")

        # 누적 합계 및 정상 측정 횟수 초기화
        sums = {ch: {'x': 0.0, 'y': 0.0, 'z': 0.0} for ch in active_sensors.keys()}
        valid_counts = {ch: 0 for ch in active_sensors.keys()}

        # 100번 반복하며 살아있는 모든 센서의 데이터를 읽음
        for _ in range(100):
            for ch, sensor in active_sensors.items():
                try:
                    x, y, z = sensor.acceleration
                    sums[ch]['x'] += x
                    sums[ch]['y'] += y
                    sums[ch]['z'] += z
                    valid_counts[ch] += 1
                except OSError:
                    # 중간에 통신 에러가 나도 무시하고 계속 진행
                    pass
            time.sleep(0.01)

        # 평균 계산 및 결과 저장
        for ch in active_sensors.keys():
            count = valid_counts[ch]
            if count == 0:
                print(f"CH{ch}: 데이터 읽기 100회 모두 실패 (통신 끊김 의심)")
                continue
                
            avg_x = sums[ch]['x'] / count
            avg_y = sums[ch]['y'] / count
            avg_z = sums[ch]['z'] / count

            # 최대/최소값 딕셔너리에 기록
            if axis == 'X' and '+1g' in desc: measurements[ch]['X_MAX'] = avg_x
            elif axis == 'X' and '-1g' in desc: measurements[ch]['X_MIN'] = avg_x
            elif axis == 'Y' and '+1g' in desc: measurements[ch]['Y_MAX'] = avg_y
            elif axis == 'Y' and '-1g' in desc: measurements[ch]['Y_MIN'] = avg_y
            elif axis == 'Z' and '+1g' in desc: measurements[ch]['Z_MAX'] = avg_z
            elif axis == 'Z' and '-1g' in desc: measurements[ch]['Z_MIN'] = avg_z

            print(f"CH{ch} 완료! (정상측정 {count}회) -> X={avg_x:.2f}, Y={avg_y:.2f}, Z={avg_z:.2f}")
        print("-" * 50)

    # 3. 오프셋 계산 및 결과 출력
    print("\n=== 최종 캘리브레이션 오프셋 결과 ===")
    print("아래 코드를 복사하여 메인 코드의 self.offsets 에 덮어씌우세요:\n")
    
    print("self.offsets = {")
    for ch in sorted(active_sensors.keys()):
        m = measurements[ch]
        try:
            offset_x = (m['X_MAX'] + m['X_MIN']) / 2.0
            offset_y = (m['Y_MAX'] + m['Y_MIN']) / 2.0
            offset_z = (m['Z_MAX'] + m['Z_MIN']) / 2.0
            print(f"    {ch}: ({offset_x:.3f}, {offset_y:.3f}, {offset_z:.3f}),")
        except KeyError:
            print(f"    # {ch}: 일부 측정 방향 데이터가 누락되어 계산할 수 없습니다.")
    print("}")

if __name__ == '__main__':
    main()
