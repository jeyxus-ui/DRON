#!/usr/bin/env python3
"""Test with FIXED stream rates (matching the backend fix)."""
import time
import sys
import threading
from pymavlink import mavutil

def read_loop(master, running, pending_acks):
    while running.is_set():
        msg = master.recv_match(blocking=False)
        if msg:
            mtype = msg.get_type()
            if mtype == "COMMAND_ACK":
                print(f"  [READ_LOOP] ACK: cmd={msg.command} result={msg.result}", flush=True)
                pending_acks[msg.command] = msg
        time.sleep(0.01)

def main():
    device = "tcp:127.0.0.1:5760"
    if len(sys.argv) > 1:
        device = sys.argv[1]

    print(f"Connecting to {device}...")
    master = mavutil.mavlink_connection(device)
    master.wait_heartbeat()
    print(f"Connected. System {master.target_system}, Component {master.target_component}")

    running = threading.Event()
    running.set()
    pending_acks = {}
    t = threading.Thread(target=read_loop, args=(master, running, pending_acks), daemon=True)
    t.start()
    print("Read loop started")

    print("\n--- Requesting streams at FIXED rates (max 5Hz) ---")
    STREAMS = [
        (mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 2),
        (mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2),
        (mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 2),
        (mavutil.mavlink.MAV_DATA_STREAM_POSITION, 5),
        (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 5),
        (mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, 2),
        (mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 1),
    ]
    for stream_id, rate_hz in STREAMS:
        master.mav.request_data_stream_send(
            master.target_system, master.target_component,
            stream_id, rate_hz, 1,
        )
    print("Fixed streams requested. Waiting 10s...")
    time.sleep(10)

    print("\n--- Test 1: SET_MODE (GUIDED) ---")
    pending_acks.clear()
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        master.mode_mapping()["GUIDED"], 0, 0, 0, 0, 0,
    )
    print("SET_MODE sent, waiting 10s...")
    deadline = time.time() + 10
    found = False
    while time.time() < deadline:
        if 176 in pending_acks:
            ack = pending_acks.pop(176)
            print(f"  ACK: cmd={ack.command} result={ack.result}")
            found = True
            break
        time.sleep(0.05)
    if not found:
        print("  NO SET_MODE ACK after 10s!")
        print(f"  pending_acks: {list(pending_acks.keys())}")

    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    if hb:
        mode_map = master.mode_mapping()
        inv = {v: k for k, v in mode_map.items()}
        print(f"  HEARTBEAT mode={inv.get(hb.custom_mode, hb.custom_mode)}")

    print("\n--- Test 2: ARM ---")
    pending_acks.clear()
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 21196, 0, 0, 0, 0, 0,
    )
    print("ARM sent, waiting 15s...")
    deadline = time.time() + 15
    found = False
    while time.time() < deadline:
        if 400 in pending_acks:
            ack = pending_acks.pop(400)
            print(f"  ACK: cmd={ack.command} result={ack.result}")
            found = True
            break
        time.sleep(0.05)
    if not found:
        print("  NO ARM ACK after 15s!")

    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    if hb:
        armed = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f"  armed={armed}")

    print("\n--- Test 3: DISARM ---")
    pending_acks.clear()
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0, 21196, 0, 0, 0, 0, 0,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if 400 in pending_acks:
            ack = pending_acks.pop(400)
            print(f"  DISARM ACK: cmd={ack.command} result={ack.result}")
            break
        time.sleep(0.05)

    running.clear()
    t.join(timeout=2)
    master.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
