#!/bin/sh
set -eu

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3가 설치되어 있지 않습니다."
  exit 1
fi

echo "ISAS 수신 서버를 시작합니다."
echo "라즈베리파이 송신 주소에는 아래 LAN IP 중 하나를 사용하십시오."
hostname -I 2>/dev/null || true
echo "웹 화면: http://localhost:8080/"
echo "같은 네트워크의 다른 장치: http://<이 노트북 LAN IP>:8080/"
echo "수신 포트: TCP 8765"

exec python3 server.py --host 0.0.0.0 --web-port 8080 --tcp-port 8765
