#!/bin/sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "사용법: $0 <우분투_노트북_IP> [MAVLink 포트] [baud]"
  echo "예: $0 192.168.0.20 /dev/serial0 57600"
  exit 2
fi

UBUNTU_IP="$1"
MAVLINK_PORT="${2:-/dev/serial0}"
MAVLINK_BAUD="${3:-57600}"
PORTABLE_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PROJECT_DIR=$(dirname "$PORTABLE_DIR")
STAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$PORTABLE_DIR/pi_logs/$STAMP"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

cleanup() {
  trap - INT TERM EXIT
  [ -n "${SENSOR_PID:-}" ] && kill "$SENSOR_PID" 2>/dev/null || true
  [ -n "${FLIGHT_PID:-}" ] && kill "$FLIGHT_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "우분투 ISAS: $UBUNTU_IP:8765"
echo "라즈베리파이 로컬 로그: $LOG_DIR"

python3 "$PORTABLE_DIR/send_to_isas.py" \
  --host "$UBUNTU_IP" --port 8765 --source pi-sensors \
  --local-log "$LOG_DIR/sensor_raw.jsonl" \
  --command "$PROJECT_DIR/sensor.py" \
  >"$LOG_DIR/sensor_sender.log" 2>&1 &
SENSOR_PID=$!

python3 "$PORTABLE_DIR/send_to_isas.py" \
  --host "$UBUNTU_IP" --port 8765 --source pi-flight \
  --local-log "$LOG_DIR/flight_raw.jsonl" \
  --command "$PORTABLE_DIR/collect_px4.py" --connection "$MAVLINK_PORT" --baud "$MAVLINK_BAUD" --rate 10 \
  >"$LOG_DIR/flight_sender.log" 2>&1 &
FLIGHT_PID=$!

echo "센서 송신 PID: $SENSOR_PID"
echo "비행정보 송신 PID: $FLIGHT_PID"
echo "종료하려면 Ctrl+C를 누르십시오."

while kill -0 "$SENSOR_PID" 2>/dev/null && kill -0 "$FLIGHT_PID" 2>/dev/null; do
  sleep 1
done

echo "송신 프로세스 하나가 종료되었습니다. 로그를 확인하십시오."
exit 1
