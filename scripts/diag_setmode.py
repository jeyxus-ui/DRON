#!/usr/bin/env python3
"""Direct pymavlink test: connect to SITL, send SET_MODE, check ACK.
Tests whether the issue is in pymavlink/SITL or in the backend code."""
import time
import sys
from pymavlink import mavutil

def main():
    device = "tcp:127.0.0.1:5760"
    if len(sys.argv) > 1:
        device = sys.argv[1]

    print(f"Connecting to {device}...")
    master = mavutil.mavlink_connection(device)
    master.wait_heartbeat()
    print(f"Connected. System {master.target_system}, Component {master.target_component}")

    print("\n--- Test 1: SET_MODE via master.set_mode() ---")
    master.set_mode(master.mode_mapping()["GUIDED"])
    print(f"SET_MODE sent (cmd=176, GUIDED={master.mode_mapping()['GUIDED']})")
    deadline = time.time() + 10
    found = False
    while time.time() < deadline:
        msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            print(f"  ACK: cmd={msg.command} result={msg.result}")
            if msg.command == 176:
                found = True
                break
    if not found:
        print("  NO SET_MODE ACK received in 10s!")

    print(f"\nCurrent mode check:")
    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    if hb:
        mode_map = master.mode_mapping()
        inv = {v: k for k, v in mode_map.items()}
        print(f"  HEARTBEAT custom_mode={hb.custom_mode} -> {inv.get(hb.custom_mode, 'UNKNOWN')}")

    print("\n--- Test 2: SET_MODE via command_long_send directly ---")
    mode_id = master.mode_mapping()["GUIDED"]
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id, 0, 0, 0, 0, 0,
    )
    print(f"command_long_send sent (cmd=176)")
    deadline = time.time() + 10
    found = False
    while time.time() < deadline:
        msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            print(f"  ACK: cmd={msg.command} result={msg.result}")
            if msg.command == 176:
                found = True
                break
    if not found:
        print("  NO SET_MODE ACK received in 10s!")

    print(f"\nCurrent mode check:")
    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    if hb:
        mode_map = master.mode_mapping()
        inv = {v: k for k, v in mode_map.items()}
        print(f"  HEARTBEAT custom_mode={hb.custom_mode} -> {inv.get(hb.custom_mode, 'UNKNOWN')}")

    print("\n--- Test 3: ARM via command_long_send ---")
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 21196, 0, 0, 0, 0, 0,
    )
    print("ARM sent")
    deadline = time.time() + 15
    found = False
    while time.time() < deadline:
        msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            print(f"  ACK: cmd={msg.command} result={msg.result}")
            if msg.command == 400:
                found = True
                break
    if not found:
        print("  NO ARM ACK received in 15s!")

    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    if hb:
        print(f"  armed={(hb.base_mode & mavutil.mavlink.MAV_SAFETY_ARMED) != 0}")

    print("\n--- Test 4: DISARM ---")
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0, 21196, 0, 0, 0, 0, 0,
    )
    print("DISARM sent")
    deadline = time.time() + 10
    while time.time() < deadline:
        msg = master.recv_match(type="COMMAND_ACK", blocking=True, timeout=2)
        if msg:
            print(f"  ACK: cmd={msg.command} result={msg.result}")
            if msg.command == 400:
                break

    master.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
