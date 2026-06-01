"""
Streaming de video y detección de objetos via OpenCV.
Incluye detección ArUco con distancia y auto-avoid.
"""

import cv2
import numpy as np
import threading
import asyncio
import base64
import logging
import time
from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse

from backend.vision.detector import VisionDetector, WARNING_DISTANCE_M

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/camera", tags=["camera"])

# ── Frame de fallback ────────────────────────────────────────
def _build_fallback_frame() -> bytes:
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, "CAMERA NOT AVAILABLE", (80, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 80, 0), 2)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes()

_FALLBACK_FRAME: bytes = _build_fallback_frame()

# Dispositivos de video a probar
VIDEO_DEVICES = [4, 2, 0, 1, 3, 5]

# Clientes WebSocket conectados
_ws_clients: set = set()


# ── Controlador de cámara ────────────────────────────────────
class RealSenseCamera:
    def __init__(self):
        self.cap           = None
        self.running       = False
        self.current_frame = None
        self.lock          = threading.Lock()
        self._device_index = None
        self._width        = 640
        self._height       = 480
        self._fps          = 30

    def start(self, width: int = 640, height: int = 480, fps: int = 30):
        self._width  = width
        self._height = height
        self._fps    = fps

        for idx in VIDEO_DEVICES:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_FPS,          fps)
                self.cap           = cap
                self._device_index = idx
                self.running       = True
                logger.info(f"✅ Cámara iniciada en /dev/video{idx} — {width}x{height} @ {fps}fps")
                break
            cap.release()

        if not self.running:
            raise RuntimeError("No device connected")

        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info("🛑 Cámara detenida")

    def _capture_loop(self):
        while self.running:
            if self.cap is None:
                break
            ret, frame = self.cap.read()
            if ret:
                markers = detector.detect(frame)
                overlay = detector.draw_overlay(frame, markers)
                _check_auto_avoid(markers)
                with self.lock:
                    self.current_frame = overlay
            else:
                logger.warning("⚠️  Frame no disponible, reintentando...")
                import time
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def get_frame_as_base64(self) -> str | None:
        frame = self.get_frame()
        if frame is None:
            return None
        small = cv2.resize(frame, (480, 360))
        ret, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ret:
            return None
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    def get_frame_with_overlay(self, telemetry=None):
        frame = self.get_frame()
        if frame is None:
            return None
        if telemetry:
            self._draw_hud(frame, telemetry)
        return frame

    def _draw_hud(self, frame, telemetry):
        h, w  = frame.shape[:2]
        font  = cv2.FONT_HERSHEY_SIMPLEX
        green = (0, 255, 0)

        cv2.putText(frame, f"ALT: {telemetry.get('altitude', 0):.1f}m",
                    (10, 30), font, 0.7, green, 2)
        cv2.putText(frame, f"SPD: {telemetry.get('ground_speed', 0):.1f}m/s",
                    (10, 60), font, 0.7, green, 2)

        bat   = telemetry.get("battery_remaining", 0)
        b_col = (0, 255, 0) if bat > 30 else (0, 165, 255) if bat > 15 else (0, 0, 255)
        cv2.putText(frame, f"BAT: {bat}%", (10, 90), font, 0.7, b_col, 2)

        cv2.putText(frame, f"MODE: {telemetry.get('mode', 'UNKNOWN')}",
                    (w - 200, 30), font, 0.7, green, 2)

        armed     = telemetry.get("armed", False)
        armed_col = (0, 0, 255) if armed else (0, 255, 0)
        cv2.putText(frame, "ARMED" if armed else "DISARMED",
                    (w - 200, 60), font, 0.7, armed_col, 2)

        cx, cy = w // 2, h // 2
        cv2.circle(frame, (cx, cy), 5, green, 2)
        cv2.line(frame, (cx - 20, cy), (cx + 20, cy), green, 2)
        cv2.line(frame, (cx, cy - 20), (cx, cy + 20), green, 2)


# ── Instancia global ─────────────────────────────────────────
camera = RealSenseCamera()
detector = VisionDetector()
_emergency_callback = None
_last_critical_time = 0


def set_emergency_callback(cb):
    global _emergency_callback
    _emergency_callback = cb
    logger.info("Emergency callback registered")


def _check_auto_avoid(markers: list) -> None:
    global _last_critical_time
    now = time.time()
    critical = [m for m in markers if m.zone == "critical"]
    if critical and (now - _last_critical_time) > 3:
        _last_critical_time = now
        logger.warning(f"CRITICAL: {len(critical)} object(s) at <{WARNING_DISTANCE_M}m")
        if _emergency_callback:
            try:
                _emergency_callback()
                logger.info("Emergency stop triggered by vision")
            except Exception as e:
                logger.error(f"Emergency callback failed: {e}")


# ── Auto-inicio ──────────────────────────────────────────────
async def startup_camera():
    try:
        if not camera.running:
            camera.start()
            logger.info("✅ Cámara iniciada automáticamente en startup")
    except Exception as e:
        logger.error(f"❌ No se pudo iniciar cámara en startup: {e}")


async def shutdown_camera():
    camera.stop()


# ── WebSocket endpoint ───────────────────────────────────────
@router.websocket("/ws")
async def camera_websocket(websocket: WebSocket):
    """
    WebSocket para streaming fluido en React Native.
    Envía frames JPEG en base64 a 25fps.
    URL: ws://IP:8000/api/camera/ws
    """
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"📡 Cliente WS conectado. Total: {len(_ws_clients)}")
    try:
        while True:
            b64 = camera.get_frame_as_base64()
            if b64:
                await websocket.send_text(b64)
            await asyncio.sleep(1 / 25)  # 25 fps
    except WebSocketDisconnect:
        logger.info("📡 Cliente WS desconectado")
    except Exception as e:
        logger.error(f"❌ Error WS: {e}")
    finally:
        _ws_clients.discard(websocket)


# ── Stream MJPEG (para navegador) ────────────────────────────
async def generate_mjpeg_stream():
    while True:
        frame = camera.get_frame()
        if frame is not None:
            ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buf.tobytes() if ret else _FALLBACK_FRAME
        else:
            frame_bytes = _FALLBACK_FRAME

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame_bytes
            + b"\r\n"
        )
        await asyncio.sleep(1 / 30)


@router.get("/stream", response_class=StreamingResponse, include_in_schema=False)
async def video_stream():
    return StreamingResponse(
        generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/view", response_class=HTMLResponse)
async def view_stream():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
  <head>
    <title>Camera Stream</title>
    <style>
      body { background:#000; margin:0; display:flex; flex-direction:column;
             justify-content:center; align-items:center; height:100vh;
             font-family:monospace; color:#0f0; }
      h2, h3 { margin:4px 0; letter-spacing:2px; }
      img { max-width:100%; max-height:70vh; border:1px solid #0f0; object-fit:contain; }
      #status, #vision { margin:2px 0; font-size:13px; }
      #vision { color:#0a0; }
      .bar { width:300px; height:6px; background:#222; margin:4px auto; border-radius:3px; overflow:hidden; }
      .bar-fill { height:100%; transition:width 0.3s; }
      .safe .bar-fill { width:0%; background:#0f0; }
      .warn .bar-fill { width:50%; background:#ffa500; }
      .crit .bar-fill { width:100%; background:#f00; }
    </style>
  </head>
  <body>
    <h2>CAMERA — LIVE</h2>
    <img id="stream" alt="Camera stream" style="background:#111;" />
    <div id="status">Conectando...</div>
    <div id="vision">Esperando deteccion...</div>
    <div id="objlist" style="margin-top:4px;font-size:11px;color:#888;max-width:90vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></div>
    <script>
      const img = document.getElementById('stream');
      const status = document.getElementById('status');
      const vision = document.getElementById('vision');
      let ok = false;
      async function refresh() {
        try {
          const ts = Date.now();
          img.src = '/api/camera/snapshot?t=' + ts;
          if (!ok) { ok = true; status.innerText = 'Stream activo'; }
        } catch(e) {
          status.innerText = 'Stream no disponible';
        }
      }
      async function pollVision() {
        try {
          const r = await fetch('/api/camera/vision');
          const d = await r.json();
          if (d.count > 0) {
            let html = d.detections.map(m =>
              m.label + ': ' + m.distance + 'm [' + m.zone + ']'
            ).join(' | ');
            vision.innerHTML = html;
            vision.style.color = d.critical_count > 0 ? '#f00' : d.warning_count > 0 ? '#ffa500' : '#0f0';
            let names = d.detections.map(function(m) { return m.label; }).filter(function(v,i,a){return a.indexOf(v)==i;}).join(', ');
            document.getElementById('objlist').innerHTML = 'Detectando: ' + names;
          } else {
            vision.innerHTML = 'Sin detecciones';
            vision.style.color = '#666';
            document.getElementById('objlist').innerHTML = '';
          }
        } catch(e) {
          vision.innerHTML = 'Error consultando vision';
        }
      }
      setInterval(refresh, 100);
      setInterval(pollVision, 500);
      pollVision();
    </script>
  </body>
</html>
""")


@router.get("/snapshot")
async def get_snapshot():
    frame = camera.get_frame()
    if frame is None:
        return Response(content="No hay frame disponible", status_code=503)
    ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ret:
        return Response(content="Error codificando imagen", status_code=500)
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.post("/start")
async def start_camera(width: int = 640, height: int = 480, fps: int = 30):
    try:
        if not camera.running:
            camera.start(width, height, fps)
            return {"success": True, "message": f"Cámara iniciada en /dev/video{camera._device_index}"}
        return {"success": False, "message": "Cámara ya está corriendo"}
    except Exception as e:
        logger.error(f"Error iniciando cámara: {e}")
        return {"success": False, "message": str(e)}


@router.post("/stop")
async def stop_camera():
    try:
        if camera.running:
            camera.stop()
            return {"success": True, "message": "Cámara detenida"}
        return {"success": False, "message": "Cámara no está corriendo"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.get("/status")
async def camera_status():
    return {
        "running":    camera.running,
        "has_frame":  camera.current_frame is not None,
        "device":     f"/dev/video{camera._device_index}" if camera._device_index is not None else None,
        "resolution": f"{camera._width}x{camera._height}",
        "fps":        camera._fps,
        "ws_clients": len(_ws_clients),
        "vision":     detector.get_status(),
    }


@router.get("/vision")
async def get_vision():
    return detector.get_status()

# Serve ArUco marker images for testing
@router.get("/markers/{marker_id}")
async def get_marker(marker_id: int):
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(base, 'assets', 'markers', f'aruco_marker_{marker_id}.png')
    if not os.path.exists(path):
        return Response(content="Marker not found", status_code=404)
    with open(path, 'rb') as f:
        data = f.read()
    return Response(content=data, media_type="image/png")
