import time
# 1. 작성한 파일에서 함수를 불러옵니다.
from rpm_check import check_motor_rpm_status

def get_motor_rpm_diff():
    """
    라즈베리파이와 연결된 센서나 ESC로부터 모터의 현재 RPM 변화량을 읽어오는 가상의 함수입니다.
    실제 환경에서는 I2C, SPI 또는 시리얼 통신 코드가 들어갑니다.
    """
    try:
        # 통신이 정상일 때의 가상 데이터 (예: Roll + 명령 수행 중)
        return 100, 120, -90, -100
    except Exception as e:
        # 통신 에러나 단선이 발생하면 None을 반환합니다.
        return None, None, None, None

def get_current_command():
    """
    현재 조종기(Tx)나 비행 제어 알고리즘에서 내리고 있는 명령을 읽어옵니다.
    """
    return 'R+'

# ==========================================
# 라즈베리파이 메인 제어 루프
# ==========================================
def main():
    print("시스템을 시작합니다...")
    
    while True:
        try:
            # 2. 통신으로 모터 상태와 현재 명령을 읽어옵니다.
            m1, m2, m3, m4 = get_motor_rpm_diff()
            current_command = get_current_command()
            
            # 3. 불러온 함수에 값을 넣어 상태를 판별합니다.
            status_msg = check_motor_rpm_status(current_command, m1, m2, m3, m4)
            
            # 4. 판별 결과를 출력하거나 로그로 남깁니다.
            print(f"현재 상태: {status_msg}")
            
            # 비정상 감지 시 안전 모드(Failsafe) 작동 로직을 추가할 수 있습니다.
            if "비정상" in status_msg or "대기 중" in status_msg:
                pass # 예: 모터 정지, 경고음 발생 등
            
            time.sleep(0.5) # 루프 주기 설정 (예: 0.5초)
            
        except KeyboardInterrupt:
            print("\n프로그램을 종료합니다.")
            break

if __name__ == "__main__":
    main()