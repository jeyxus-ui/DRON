#!/bin/bash
cd /mnt/c/Users/USUARIO/Desktop/Drones/dron\ r/Dron/scripts
python3 bridge_wsl.py 2>&1 | tee /tmp/bridge.log
