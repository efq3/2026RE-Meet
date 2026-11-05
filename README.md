# 2026 RE-Meet — ISAS

ISAS (Integrated Status Assessment System, 통합 상태 평가 시스템)는 X8 기체의 암대별 온도와 가속도를 수집하고, 지상 PC에서 3축 RMS를 계산하여 숫자와 그래프로 표시하는 연구용 시스템입니다.

실기체 암대 1~4의 IMU 순서는 **IMU1, IMU3, IMU2, IMU4**입니다. 계산 설정과 라벨 정의는 [센서 매핑](isas_portable/SENSOR_MAPPING.md)에 기록합니다.

```text
암대 IMU·온도 + Pixhawk
  → 라즈베리파이: 센서 수집·원본 저장·TCP 송신
  → 우분투 PC: 원본 저장·RMS 계산·상태 평가
  → 웹브라우저: 4개 암대 온도·RMS 숫자 및 그래프
```

## 우분투 PC: 수신·계산·화면 실행

Python 3.10 이상이 필요합니다. PC 수신 서버에는 추가 Python 패키지가 필요하지 않습니다.

최초 설치:

```bash
git clone https://github.com/efq3/2026RE-Meet.git
cd 2026RE-Meet
sh isas_portable/START_UBUNTU_ISAS.sh
```

이미 저장소가 있다면 해당 폴더에서:

```bash
git pull --ff-only
sh isas_portable/START_UBUNTU_ISAS.sh
```

웹 화면은 `http://localhost:8080/`입니다. 프로그램을 실행한 터미널은 유지합니다. 서버는 데이터 입력용 TCP 8765와 웹 화면용 TCP 8080을 사용합니다.

## 라즈베리파이: 센서·비행정보 송신

기존 센서 라이브러리와 `pymavlink`를 사용하는 환경에서 실행합니다. 센서와 시리얼 포트를 사용 중인 기존 수집기를 먼저 종료합니다.

```bash
cd ~/2026RE-Meet
git pull --ff-only
sh isas_portable/START_PI_STREAMS.sh <우분투_PC_IP> /dev/serial0 57600
```

`<우분투_PC_IP>`를 라즈베리파이에서 접근 가능한 **ISAS 수신 PC의 IPv4 주소**로 바꿉니다. 예를 들어 PC 주소가 `192.168.137.20`이면:

```bash
sh isas_portable/START_PI_STREAMS.sh 192.168.137.20 /dev/serial0 57600
```

우분투가 가상머신이면 라즈베리파이에서 VM의 TCP 8765에 접근 가능한 네트워크 구성이 필요합니다. 라즈베리파이에서 다음으로 먼저 확인할 수 있습니다.

```bash
nc -vz -w 3 192.168.137.20 8765
```

센서 수집·송신은 부팅 후 위 명령을 실행해야 시작됩니다. SSH는 라즈베리파이에 접속해 명령을 실행하는 용도로 사용할 수 있습니다.

## 핵심 코드

| 위치 | 역할 |
|---|---|
| `imu_sensor.py`, `temp_sensor.py`, `sensor.py` | 4개 암대 센서 수집·출력 |
| `isas_portable/send_to_isas.py` | JSONL 송신과 Pi 로컬 원본 기록 |
| `isas_portable/collect_px4.py` | MAVLink Armed·자세·각속도 등 실제 수신값 전달 |
| `isas_portable/server.py` | PC TCP 수신·로그 저장·웹 서버 |
| `isas_portable/logic.py` | 평균 제거 3축 RMS·수집률·상대 온도·이상 후보 계산 |
| `isas_portable/config.json` | 계산창·임계값·지속시간 설정 |
| `isas_portable/web/` | 온도·RMS 숫자, 그래프, 연결·비행 상태 표시 |

RMS는 PC에서 최근 2초의 각 축 평균을 제거한 가속도 변동으로 계산하며, 단위는 m/s²입니다. 원본은 들어오는 속도로 저장하고, 계산 결과와 웹 화면은 약 5 Hz로 갱신합니다. 비행 상태가 부족하거나 기동 중이라 진동 이상 판정을 보류하더라도 온도와 유효한 RMS는 표시합니다.

현재 센서 코드는 ±16 g 범위를 명시합니다. 센서 ODR과 실제 수집률은 별개이며 실제 수집률은 타임스탬프로 확인합니다. 기체 운동 보정과 정상 기동 모델은 아직 적용되지 않았고, 임계값은 검증 전입니다.

로그 위치와 입력 형식, 연결 시험 및 상세 사용법은 [isas_portable/README.md](isas_portable/README.md)를 참고합니다.
