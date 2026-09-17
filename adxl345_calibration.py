import smbus2
import time
import struct

# I2C 설정 (Raspberry Pi의 경우 기본적으로 버스 1 사용)
I2C_BUS = 1
ADXL345_ADDR = 0x53  # 센서에 따라 0x1D일 수 있습니다.

# ADXL345 레지스터 주소
POWER_CTL = 0x2D
DATA_FORMAT = 0x31
DATA_X0 = 0x32

# 1g에 해당하는 이상적인 LSB 값 (±2g 범위, 10비트 분해능 기준)
IDEAL_1G = 256.0 

bus = smbus2.SMBus(I2C_BUS)

def init_adxl345():
    """센서 초기화 및 측정 모드 진입"""
    # 데이터 포맷 설정: ±2g 범위, 10비트 모드
    bus.write_byte_data(ADXL345_ADDR, DATA_FORMAT, 0x00)
    # 측정 모드 활성화
    bus.write_byte_data(ADXL345_ADDR, POWER_CTL, 0x08)
    time.sleep(0.1)

def read_raw_data():
    """X, Y, Z축의 Raw 데이터를 읽어옵니다."""
    data = bus.read_i2c_block_data(ADXL345_ADDR, DATA_X0, 6)
    # 16비트 리틀 엔디안(Little Endian) 2의 보수 형태로 패킹 해제
    x, y, z = struct.unpack('<hhh', bytes(data))
    return x, y, z

def collect_data(samples=100, delay=0.01):
    """지정된 횟수만큼 데이터를 수집하여 평균값을 반환합니다."""
    x_sum, y_sum, z_sum = 0, 0, 0
    for _ in range(samples):
        x, y, z = read_raw_data()
        x_sum += x
        y_sum += y
        z_sum += z
        time.sleep(delay)
    return x_sum / samples, y_sum / samples, z_sum / samples

def main():
    init_adxl345()
    print("=== ADXL345 6면 캘리브레이션을 시작합니다 ===")
    print("각 축이 중력(바닥)을 향하도록 센서를 배치한 후 Enter를 누르세요.\n")

    measurements = {}

    # 6개 방향에 대한 데이터 수집 지침
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
        avg_x, avg_y, avg_z = collect_data()
        
        # 주축에 해당하는 데이터만 저장
        if axis == 'X' and '+1g' in desc: measurements['X_MAX'] = avg_x
        elif axis == 'X' and '-1g' in desc: measurements['X_MIN'] = avg_x
        elif axis == 'Y' and '+1g' in desc: measurements['Y_MAX'] = avg_y
        elif axis == 'Y' and '-1g' in desc: measurements['Y_MIN'] = avg_y
        elif axis == 'Z' and '+1g' in desc: measurements['Z_MAX'] = avg_z
        elif axis == 'Z' and '-1g' in desc: measurements['Z_MIN'] = avg_z
        
        print(f"완료! 측정값: X={avg_x:.1f}, Y={avg_y:.1f}, Z={avg_z:.1f}\n")

    # 오프셋 및 스케일 팩터 계산
    offset_x = (measurements['X_MAX'] + measurements['X_MIN']) / 2.0
    offset_y = (measurements['Y_MAX'] + measurements['Y_MIN']) / 2.0
    offset_z = (measurements['Z_MAX'] + measurements['Z_MIN']) / 2.0

    scale_x = (IDEAL_1G * 2) / (measurements['X_MAX'] - measurements['X_MIN'])
    scale_y = (IDEAL_1G * 2) / (measurements['Y_MAX'] - measurements['Y_MIN'])
    scale_z = (IDEAL_1G * 2) / (measurements['Z_MAX'] - measurements['Z_MIN'])

    print("=== 캘리브레이션 결과 ===")
    print("이 값을 비행 제어 코드나 ROS 2 노드의 파라미터로 저장하여 사용하세요.")
    print(f"OFFSET_X = {offset_x:.2f}")
    print(f"OFFSET_Y = {offset_y:.2f}")
    print(f"OFFSET_Z = {offset_z:.2f}")
    print(f"SCALE_X  = {scale_x:.4f}")
    print(f"SCALE_Y  = {scale_y:.4f}")
    print(f"SCALE_Z  = {scale_z:.4f}")

    print("\n[코드 적용 예시]")
    print("calibrated_x = (raw_x - OFFSET_X) * SCALE_X")
    print("calibrated_y = (raw_y - OFFSET_Y) * SCALE_Y")
    print("calibrated_z = (raw_z - OFFSET_Z) * SCALE_Z")

if __name__ == '__main__':
    main()