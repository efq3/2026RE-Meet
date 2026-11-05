# ISAS PC 수신·RMS 계산·실시간 모니터

## 장치별 역할

```text
라즈베리파이: sensor.py → send_to_isas.py ──────┐
라즈베리파이: collect_px4.py → send_to_isas.py ─┤ TCP JSONL :8765
                                               ↓
우분투 PC: server.py → logic.py → HTTP/SSE :8080 → 브라우저
```

- 라즈베리파이는 암대 센서와 Pixhawk의 실제 수신 데이터를 보냅니다.
- PC는 원본을 저장하고 최근 2초 창의 평균 제거 3축 RMS를 계산합니다.
- 브라우저는 4개 암대의 온도·RMS 숫자와 그래프, 수집률 및 상태를 약 5 Hz로 표시합니다.
- 온도나 비행 정보 일부가 없어도 유효한 IMU의 RMS는 계산합니다. 초기화 문자열·오류·결측을 숫자 0으로 대체하지 않습니다.
- 브라우저를 닫아도 PC 서버가 실행 중이면 수신·계산·저장은 계속됩니다.

## 우분투 PC에서 실행

저장소 루트에서:

```bash
git pull --ff-only
sh isas_portable/START_UBUNTU_ISAS.sh
```

최초 설치는 먼저 저장소를 복제합니다.

```bash
git clone https://github.com/efq3/2026RE-Meet.git
cd 2026RE-Meet
sh isas_portable/START_UBUNTU_ISAS.sh
```

Python 3.10 이상이 필요하며 PC 서버는 Python 표준 라이브러리만 사용합니다. 센서용 라이브러리와 pymavlink는 라즈베리파이에서 필요합니다.

브라우저 주소: `http://localhost:8080/`.
다른 장치에서 볼 때는 `http://<우분투_PC_IP>:8080/`을 사용합니다.
서버를 실행한 터미널은 유지합니다. Ctrl+C로 종료합니다.

Windows는 `isas_portable/START_WINDOWS.cmd`, Linux/macOS 공통 실행은 `sh isas_portable/start_linux_mac.sh`를 사용할 수도 있습니다.

## 라즈베리파이에서 송신

같은 센서 프로그램과 시리얼 포트를 이미 사용하는 수집기가 있다면 종료한 뒤, 저장소 루트에서:

```bash
git pull --ff-only
sh isas_portable/START_PI_STREAMS.sh <우분투_PC_IP> /dev/serial0 57600
```

예를 들어 우분투 PC 주소가 `192.168.137.20`이면:

```bash
sh isas_portable/START_PI_STREAMS.sh 192.168.137.20 /dev/serial0 57600
```

이 스크립트가 `sensor.py`와 `collect_px4.py`를 함께 실행하고 각각 송신합니다. `sensor.py`의 한 줄 JSON 표준출력을 유지해야 합니다.

센서 전용 송신 또는 기존 프로그램 연결도 가능합니다. `--command`는 마지막 옵션에 둡니다.

```bash
python3 isas_portable/send_to_isas.py --host 192.168.137.20 --source pi-sensors --local-log sensor_raw.jsonl --command sensor.py
```

별도 MAVLink 송신:

```bash
python3 isas_portable/send_to_isas.py --host 192.168.137.20 --source pi-flight --local-log flight_raw.jsonl --command isas_portable/collect_px4.py --connection /dev/serial0 --baud 57600
```

`collect_px4.py`는 수신 전용 MAVLink 어댑터입니다. 이름에 px4가 있지만 HEARTBEAT와 ATTITUDE 등 공통 메시지를 읽습니다. FC의 메시지 송출률을 자동 변경하지 않으므로 실제 필드 수신 여부를 확인해야 합니다. 수신되지 않은 필드는 생성하지 않습니다.

기존 `flight.py`의 `pixhawk` JSON도 읽을 수 있지만, 그 출력에는 Armed와 각속도가 없어 진동 이상 후보 판정은 보류됩니다. 온도·RMS 표시는 계속됩니다.

## 네트워크 확인

라즈베리파이에서 우분투 PC의 TCP 8765에 접근 가능해야 합니다. 다음 주소는 예시입니다.

```bash
nc -vz -w 3 192.168.137.20 8765
```

우분투 PC에서 수신 포트를 확인합니다.

```bash
ss -ltnp | grep -E '8080|8765'
```

게스트 Wi-Fi의 장치 간 통신 차단이나 가상머신 NAT는 연결을 막을 수 있습니다. 같은 실험 LAN 또는 접근 가능한 브리지 네트워크를 사용하고, 필요한 방화벽 규칙은 실험망으로 제한합니다. 현재 서버에는 로그인 인증이 없으므로 인터넷에 공개하지 않습니다.

8080/8765가 다른 프로그램에서 사용 중이면 직접 포트를 지정할 수 있습니다. 송신기에도 같은 TCP 포트를 사용합니다.

```bash
python3 isas_portable/server.py --web-port 8090 --tcp-port 8766
```

## 화면과 판정

- 각 Arm 카드: 온도(°C), 평균 제거 3축 RMS(m/s²), 상대 RMS·온도 상승량, 타임스탬프 기반 기록률, 상태.
- 그래프: 최근 120초의 온도와 RMS. 가로축은 PC 수신 시각입니다.
- `현재 온도를 비교 기준으로 설정`: 현재 유효한 온도 4개를 시작 기준으로 저장합니다.
- `새 시험 시작`: 계산창·온도 기준·판정 타이머를 초기화합니다. 로그 파일은 바뀌지 않습니다. 별도 파일 세트가 필요하면 서버를 재시작합니다.
- `원본 로그`, `시험 로그 전체 ZIP`: 현재 서버 실행 세션의 자료를 내려받습니다.
- 실제 Armed=false이면 DISARMED, 비행 정보가 없으면 context_missing, 큰 기동 중이면 maneuver로 진동 판정을 보류합니다. 이때도 유효한 RMS와 온도는 표시합니다.

현재 지표는 필터 미적용 가속도 변동 RMS입니다. 기체 운동 보정, 정상 기동별 예상 RMS 모델 및 검증된 고장 진단은 아직 포함되지 않았습니다. 자세한 정의와 기본값은 [LOGIC_SPEC.md](LOGIC_SPEC.md)에 있습니다.

## 입력 JSONL 형식

JSON 객체 하나를 UTF-8 한 줄로 보내고 줄바꿈 `\n`을 붙입니다. 아래 예시는 한 줄입니다.

```json
{"timestamp":1793453475.978,"imu":{"CH0":{"X":0.1,"Y":0.2,"Z":9.8},"CH1":{"X":0.2,"Y":0.1,"Z":9.7},"CH2":{"X":0.1,"Y":0.3,"Z":9.8},"CH3":{"X":0.2,"Y":0.2,"Z":9.9}},"temperature":{"S1":25.1,"S2":25.2,"S3":25.0,"S4":25.3}}
```

- CH0/S1 = Arm 1, CH1/S2 = Arm 2, CH2/S3 = Arm 3, CH3/S4 = Arm 4.
- 가속도는 m/s², 온도는 °C, timestamp는 Unix 초입니다. ISO 8601 시각 문자열도 수용합니다.
- `temperature_timestamp`는 실제 온도 갱신 시각 또는 S1~S4별 시각 객체입니다. 없으면 온도 갱신 시각 미확인으로 표시합니다.
- 온도 초기화 문자열이나 개별 채널 오류가 있어도 다른 유효 채널은 유지합니다.
- 실제 FC 정보는 별도 JSONL 스트림으로 같은 수신기에 보낼 수 있습니다.

```json
{"timestamp":1793453475.980,"flight_context":{"armed":true,"flight_mode":"LOITER","attitude_deg":{"roll":0.2,"pitch":0.1,"yaw":15.0},"angular_velocity_rad_s":{"x":0.01,"y":0.02,"z":0.0}}}
```

새 필드를 임의로 0이나 true로 채우지 않습니다. 소스 시각·전송 시각·수신 시각은 서로 다른 의미이며, 수신률이 센서 내부 ODR을 입증하지는 않습니다.

## 로그 저장

PC는 `isas_portable/logs/`에 실행별 파일을 만듭니다.

| 파일 | 내용 |
|---|---|
| `raw_*.jsonl` | 받은 원본 JSON 패킷과 전달 메타데이터 |
| `receipt_*.jsonl` | 패킷 번호·PC 수신 시각·송신 주소 |
| `features_*.jsonl` | 약 5 Hz 계산·표시·후보 상태 |
| `config_*.json` | 서버 실행 당시 계산 설정 |

Pi 실행 스크립트는 `isas_portable/pi_logs/<실행시각>/`에 `sensor_raw.jsonl`, `flight_raw.jsonl`, 송신기 로그를 남깁니다. 네트워크가 끊겨도 Pi 입력 수집과 로컬 기록은 계속하고 송신기는 재접속합니다. 전송 대기열은 2000패킷으로 제한되므로 오래된 패킷이 누락될 수 있습니다. 로컬 원본과 수신 원본을 함께 보존합니다. TCP 전송 성공은 PC 디스크 영구 저장 확인 응답이 아닙니다.

`flush()`는 Python 파일 버퍼를 운영체제로 전달하는 동작입니다. 전원 차단에도 보존되는 영구 저장을 보장하는 `fsync()`와는 다릅니다.

## 센서 없이 화면 확인

PC 수신 서버를 먼저 실행한 뒤 다른 터미널에서:

```bash
python3 isas_portable/send_to_isas.py --host 127.0.0.1 --source demo --demo --rate 125
```

화면에 DEMO가 표시되고 약 10초부터 Arm 3의 가상 온도·진동이 상승합니다. 실측 결과가 아닙니다. 실측 송신기와 데모를 동시에 연결하지 않습니다.

저장 파일을 화면에 재생할 때:

```bash
python3 isas_portable/send_to_isas.py --host 127.0.0.1 --source replay --file sensor_log.txt --rate 125
```

`--rate`는 초당 전송 줄 수이며 원래 타임스탬프를 변경하지 않습니다. 원래 비행 간격과 판정 지연을 재현하는 정량 재생기는 아닙니다.

## 선택 기능: SSH로 stdout 읽기

직접 TCP 송신 대신 PC에서 SSH 접속으로 기존 한 줄 JSON 출력을 읽을 수도 있습니다.

```bash
python3 isas_portable/server.py --host 127.0.0.1 --ssh user@pi-address --ssh-command "cd /home/user/2026RE-Meet && python3 -u sensor.py"
```

이 모드에서는 TCP 8765 수신기를 열지 않습니다. TCP 방식과 같은 센서 수집기를 중복 실행하지 않습니다. 대화형 실행은 `python3 isas_portable/start_ssh.py`를 사용할 수 있습니다. 비밀번호와 개인키 내용은 저장하지 않으며 접속 설정 파일은 Git에 포함하지 않습니다.

## 확인 및 배포

```bash
cd isas_portable
python3 -m unittest -v test_logic.py test_server.py
python3 build_package.py
```

배포 ZIP에는 실행 코드·웹 파일·설정·문서를 넣고 로그·캐시·로컬 SSH 설정은 제외합니다.
