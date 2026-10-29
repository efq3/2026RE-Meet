"""Receive MAVLink and print independently timestamped ISAS flight context JSONL."""

import argparse
import json
import math
import sys
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--connection",default="/dev/serial0")
    parser.add_argument("--baud",type=int,default=57600)
    parser.add_argument("--rate",type=float,default=10)
    args=parser.parse_args()
    if args.rate<=0:
        parser.error("rate must be positive")
    try:
        from pymavlink import mavutil
    except ImportError:
        raise SystemExit("Install pymavlink on the Pi: python3 -m pip install pymavlink")
    link=mavutil.mavlink_connection(args.connection,baud=args.baud)
    print("Waiting for Pixhawk heartbeat",file=sys.stderr,flush=True)
    heartbeat=link.wait_heartbeat(timeout=15)
    if heartbeat is None:
        raise SystemExit("No heartbeat; check connection, baud and configured MAVLink streams")
    target_system=heartbeat.get_srcSystem()
    target_component=heartbeat.get_srcComponent()
    values={}
    updated={}

    def save(key,value):
        values[key]=value
        updated[key]=time.monotonic()

    def receive(message):
        if message.get_srcSystem()!=target_system or message.get_srcComponent()!=target_component:
            return
        kind=message.get_type()
        if kind=="HEARTBEAT":
            save("armed",bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))
            save("flight_mode",mavutil.mode_string_v10(message))
        elif kind=="ATTITUDE":
            save("attitude_deg",{a:math.degrees(float(getattr(message,a))) for a in ("roll","pitch","yaw")})
            save("angular_velocity_rad_s",dict(zip("xyz",(float(message.rollspeed),float(message.pitchspeed),float(message.yawspeed)))))
            save("attitude_time_boot_ms",int(message.time_boot_ms))
        elif kind=="VFR_HUD":
            save("throttle_pct",float(message.throttle))
        elif kind=="SYS_STATUS":
            if message.voltage_battery!=65535:
                save("battery_voltage_v",float(message.voltage_battery)/1000)
        elif kind=="EXTENDED_SYS_STATE":
            save("landed_state",int(message.landed_state))
        elif kind=="SERVO_OUTPUT_RAW":
            # These are actuator output commands, never measured RPM.
            save("actuator_output_pwm_us",[getattr(message,f"servo{i}_raw",None) for i in range(1,9)])
            save("actuator_port",int(message.port))

    receive(heartbeat)
    next_print=time.monotonic()
    try:
        while True:
            message=link.recv_match(blocking=True,timeout=.02)
            if message is not None:
                receive(message)
            now=time.monotonic()
            if now>=next_print:
                # Do not refresh old ATTITUDE/HEARTBEAT fields just by republishing them.
                context={k:v for k,v in values.items() if now-updated[k] < (3 if k in ("armed","flight_mode") else 1)}
                packet={"timestamp":time.time(),"flight_context":context,
                        "context_field_age_s":{k:round(now-updated[k],4) for k in context}}
                try:
                    print(json.dumps(packet,allow_nan=False),flush=True)
                except ValueError:
                    print("Skipped nonfinite MAVLink values",file=sys.stderr,flush=True)
                next_print=now+1/args.rate
    except KeyboardInterrupt:
        pass
    finally:
        link.close()


if __name__=="__main__":
    main()
