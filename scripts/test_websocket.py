#!/usr/bin/env python3
"""
WebSocket Troubleshooting & Test Script
========================================
Simula exactamente lo que hace la app móvil:
  1. Conecta al WebSocket ws://<HOST>:8000/ws/telemetry
  2. Escucha telemetría durante N segundos
  3. Envía un comando RC_CONTROL (como el joystick)
  4. Verifica que el WebSocket NO se desconecte tras el envío
  5. Continúa recibiendo telemetría después del comando

Uso:
    python scripts/test_websocket.py                        # usa 192.168.137.22
    python scripts/test_websocket.py --host 192.168.1.105   # IP personalizada
    python scripts/test_websocket.py --host localhost        # prueba local

Requiere: pip install websockets requests
"""

import asyncio
import json
import sys
import time
import argparse
import traceback

try:
    import websockets
except ImportError:
    print("❌ Falta 'websockets'. Instala con: pip install websockets")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ Falta 'requests'. Instala con: pip install requests")
    sys.exit(1)


# ─── Configuración ────────────────────────────────────────────────────────────

DEFAULT_HOST = "192.168.137.22"
DEFAULT_PORT = 8000

# ─── Helpers ──────────────────────────────────────────────────────────────────

def ts():
    return time.strftime("%H:%M:%S")

def ok(msg):  print(f"[{ts()}] ✅  {msg}")
def warn(msg): print(f"[{ts()}] ⚠️  {msg}")
def err(msg):  print(f"[{ts()}] ❌  {msg}")
def info(msg): print(f"[{ts()}] ℹ️  {msg}")

# ─── Test 1: HTTP health check ────────────────────────────────────────────────

def test_http(host, port):
    print("\n" + "="*60)
    print("TEST 1 — HTTP Health Check")
    print("="*60)
    base = f"http://{host}:{port}"
    endpoints = ["/", "/health", "/api/status"]
    all_ok = True
    for ep in endpoints:
        url = base + ep
        try:
            r = requests.get(url, timeout=5)
            ok(f"GET {ep} → {r.status_code}")
        except requests.exceptions.ConnectionError:
            err(f"GET {ep} → No se pudo conectar a {url}")
            all_ok = False
        except requests.exceptions.Timeout:
            err(f"GET {ep} → Timeout (>5s)")
            all_ok = False
        except Exception as e:
            err(f"GET {ep} → {e}")
            all_ok = False
    return all_ok

# ─── Test 2: WebSocket connect + telemetry ────────────────────────────────────

async def test_ws_connect_and_telemetry(host, port, listen_seconds=5):
    print("\n" + "="*60)
    print(f"TEST 2 — WebSocket: conectar y recibir telemetría ({listen_seconds}s)")
    print("="*60)
    uri = f"ws://{host}:{port}/ws/telemetry"
    info(f"Conectando a {uri} ...")

    telemetry_count = 0
    start = time.time()

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            ok(f"Conexión WebSocket establecida")

            while time.time() - start < listen_seconds:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    if msg.get("type") == "telemetry":
                        telemetry_count += 1
                        if telemetry_count == 1:
                            ok(f"Primer mensaje de telemetría recibido: {list(msg.get('data', {}).keys())}")
                        elif telemetry_count % 10 == 0:
                            info(f"Telemetría recibida: {telemetry_count} mensajes")
                    else:
                        info(f"Mensaje tipo '{msg.get('type')}': {str(msg)[:100]}")
                except asyncio.TimeoutError:
                    warn("No se recibió mensaje en 2s (puede ser normal si no hay dron conectado)")
                except json.JSONDecodeError as e:
                    err(f"JSON inválido recibido: {e}")

            ok(f"Total telemetría recibida en {listen_seconds}s: {telemetry_count} mensajes")
            if telemetry_count == 0:
                warn("No se recibió telemetría — el backend puede estar en modo SIM sin dron")
            return True

    except websockets.exceptions.ConnectionRefusedError:
        err(f"Conexión rechazada en {uri}")
        err("Verifica que el backend esté corriendo: docker-compose up backend")
        return False
    except websockets.exceptions.InvalidURI:
        err(f"URI inválida: {uri}")
        return False
    except Exception as e:
        err(f"Error conectando WebSocket: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

# ─── Test 3: Enviar comando y verificar que NO se desconecte ─────────────────

async def test_ws_send_command_no_disconnect(host, port):
    print("\n" + "="*60)
    print("TEST 3 — WebSocket: enviar comando RC_CONTROL y verificar que NO se desconecte")
    print("="*60)
    uri = f"ws://{host}:{port}/ws/telemetry"
    info(f"Conectando a {uri} ...")

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            ok("Conexión establecida")

            # Esperar primer mensaje de telemetría (o timeout)
            info("Esperando primer mensaje del servidor...")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = json.loads(raw)
                ok(f"Primer mensaje recibido: tipo='{msg.get('type')}'")
            except asyncio.TimeoutError:
                warn("No llegó mensaje inicial en 3s, continuando de todas formas...")

            # Enviar comando RC_CONTROL (igual que el joystick de la app)
            command = {
                "type": "RC_CONTROL",
                "params": {
                    "throttle": 0.5,
                    "yaw": 0.0,
                    "pitch": 0.1,
                    "roll": 0.0
                }
            }
            info(f"Enviando comando: {json.dumps(command)}")
            await ws.send(json.dumps(command))
            ok("Comando enviado")

            # Esperar ACK
            info("Esperando ACK del servidor...")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                if msg.get("type") == "command_ack":
                    ok(f"ACK recibido: comando='{msg.get('command')}' resultado={msg.get('result')}")
                else:
                    info(f"Mensaje recibido (no ACK): {str(msg)[:200]}")
            except asyncio.TimeoutError:
                err("No se recibió ACK en 5s — posible desconexión o error en el backend")
                return False

            # Verificar que la conexión sigue activa recibiendo más mensajes
            info("Verificando que la conexión sigue activa (5s más)...")
            post_command_count = 0
            start = time.time()
            while time.time() - start < 5.0:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    if msg.get("type") == "telemetry":
                        post_command_count += 1
                except asyncio.TimeoutError:
                    pass
                except websockets.exceptions.ConnectionClosed as e:
                    err(f"WebSocket CERRADO después del comando: code={e.code} reason='{e.reason}'")
                    return False

            if post_command_count > 0:
                ok(f"Conexión activa después del comando: {post_command_count} mensajes de telemetría recibidos")
            else:
                warn("No se recibió telemetría post-comando (puede ser normal en modo SIM)")

            ok("TEST 3 PASADO — El WebSocket NO se desconectó al enviar el comando")
            return True

    except websockets.exceptions.ConnectionRefusedError:
        err(f"Conexión rechazada en {uri}")
        return False
    except websockets.exceptions.ConnectionClosed as e:
        err(f"WebSocket cerrado inesperadamente: code={e.code} reason='{e.reason}'")
        return False
    except Exception as e:
        err(f"Error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

# ─── Test 4: Enviar múltiples comandos rápidos (stress test) ─────────────────

async def test_ws_rapid_commands(host, port, count=10):
    print("\n" + "="*60)
    print(f"TEST 4 — Stress: enviar {count} comandos rápidos consecutivos")
    print("="*60)
    uri = f"ws://{host}:{port}/ws/telemetry"

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            ok("Conexión establecida")
            acks_received = 0

            for i in range(count):
                command = {
                    "type": "RC_CONTROL",
                    "params": {
                        "throttle": round(i / count, 2),
                        "yaw": 0.0,
                        "pitch": 0.0,
                        "roll": 0.0
                    }
                }
                await ws.send(json.dumps(command))
                info(f"Comando {i+1}/{count} enviado")

                # Recoger respuestas (puede ser telemetría o ACK)
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    msg = json.loads(raw)
                    if msg.get("type") == "command_ack":
                        acks_received += 1
                    # Si es telemetría, intentar recibir el ACK también
                    elif msg.get("type") == "telemetry":
                        try:
                            raw2 = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            msg2 = json.loads(raw2)
                            if msg2.get("type") == "command_ack":
                                acks_received += 1
                        except asyncio.TimeoutError:
                            pass
                except asyncio.TimeoutError:
                    warn(f"Timeout esperando respuesta al comando {i+1}")
                except websockets.exceptions.ConnectionClosed as e:
                    err(f"WebSocket CERRADO en comando {i+1}: code={e.code}")
                    return False

                await asyncio.sleep(0.1)  # 100ms entre comandos (igual que el joystick)

            ok(f"Stress test completado: {acks_received}/{count} ACKs recibidos")
            return True

    except Exception as e:
        err(f"Error en stress test: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(host, port):
    print("\n" + "█"*60)
    print(f"  WEBSOCKET TROUBLESHOOTING — {host}:{port}")
    print("█"*60)

    results = {}

    # Test 1: HTTP
    results["HTTP Health"] = test_http(host, port)

    # Test 2: WS telemetría
    results["WS Telemetría"] = await test_ws_connect_and_telemetry(host, port, listen_seconds=5)

    # Test 3: Enviar comando sin desconexión
    results["WS Comando sin desconexión"] = await test_ws_send_command_no_disconnect(host, port)

    # Test 4: Stress
    results["WS Stress (10 comandos)"] = await test_ws_rapid_commands(host, port, count=10)

    # Resumen
    print("\n" + "="*60)
    print("RESUMEN DE TESTS")
    print("="*60)
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASÓ" if passed else "❌ FALLÓ"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        ok("Todos los tests pasaron — el WebSocket funciona correctamente")
    else:
        err("Algunos tests fallaron — revisa los logs del backend con:")
        print("      docker-compose logs -f backend")
        print()
        print("  Causas comunes de desconexión al enviar comandos:")
        print("  1. Escrituras concurrentes (broadcaster + ACK) → ya corregido con asyncio.Lock")
        print("  2. Excepción en process_command sin capturar → revisa logs del backend")
        print("  3. Timeout de red (firewall, NAT) → verifica que el puerto 8000 esté abierto")
        print("  4. El backend no tiene MAVLink conectado → modo SIM activo, RC_CONTROL falla")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket Troubleshooting Tool")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"IP del backend (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto del backend (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port))
