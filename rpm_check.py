def check_motor_rpm_status(command, m1_diff, m2_diff, m3_diff, m4_diff):
    """
    command: 'R+', 'R-', 'P+', 'P-', 'Y+', 'Y-' (Roll, Pitch, Yaw 명령)
    m1_diff ~ m4_diff: 기본 RPM 대비 각 모터의 RPM 변화량. 
                       데이터가 아직 없거나 연결 전이면 None을 전달.
    """
    
    # 1. 데이터 수신 여부 확인 (연결 대기 상태)
    if None in (m1_diff, m2_diff, m3_diff, m4_diff):
        return "모터 데이터 수신 대기 중... (통신 연결 확인 필요)"

    # image.png 메모장에 적힌 RPY 모터 증감 규칙 정의
    rules = {
        'R+': ([1, 2], [3, 4]),
        'R-': ([3, 4], [1, 2]),
        'P+': ([1, 4], [2, 3]),
        'P-': ([2, 3], [1, 4]),
        'Y+': ([1, 3], [2, 4]),
        'Y-': ([2, 4], [1, 3])
    }
    
    if command not in rules:
        return "알 수 없는 명령입니다."
        
    increase_motors, decrease_motors = rules[command]
    
    # 각 모터 번호와 변화량을 매핑
    rpm_diffs = {1: m1_diff, 2: m2_diff, 3: m3_diff, 4: m4_diff}
    
    is_normal = True
    faulty_motors = []
    
    # 2. 높아져야 하는 모터가 낮아진 경우 체크
    for m in increase_motors:
        if rpm_diffs[m] < 0:
            is_normal = False
            faulty_motors.append(f"{m}번(증가 필요, 현재 감소)")
            
    # 3. 낮아져야 하는 모터가 높아진 경우 체크
    for m in decrease_motors:
        if rpm_diffs[m] > 0:
            is_normal = False
            faulty_motors.append(f"{m}번(감소 필요, 현재 증가)")
            
    # 결과 출력
    if is_normal:
        return f"[{command} 상태] 정상"
    else:
        return f"[{command} 상태] 비정상 -> 문제 모터: {', '.join(faulty_motors)}"

# ==========================================
# 테스트 예시
# ==========================================
if __name__ == "__main__":
    # 예시 1: 데이터가 아직 들어오지 않은 초기 상태 (None 전달)
    print(check_motor_rpm_status('R+', None, None, None, None))
    
    # 예시 2: 일부 모터 데이터만 누락된 경우 (통신 불안정)
    print(check_motor_rpm_status('P+', 50, None, 40, -30))

    # 예시 3: 데이터가 정상적으로 들어오고 상태도 정상인 경우
    print(check_motor_rpm_status('R+', 100, 120, -90, -100))