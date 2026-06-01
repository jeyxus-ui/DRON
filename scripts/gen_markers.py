import cv2
import numpy as np

DICT = cv2.aruco.DICT_6X6_250
dict = cv2.aruco.getPredefinedDictionary(DICT)

for marker_id in [0, 1, 42]:
    inner = cv2.aruco.generateImageMarker(dict, marker_id, 300)
    border_px = 100
    size = inner.shape[0] + 2 * border_px
    canvas = np.ones((size, size), dtype=np.uint8) * 255
    canvas[border_px:border_px+inner.shape[0], border_px:border_px+inner.shape[0]] = inner

    marker_bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    cv2.putText(marker_bgr, f'ID {marker_id} - DICT 6X6_250', (30, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(marker_bgr, 'Usar a 15cm para distancia', (30, size - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    import os
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', 'markers')
    os.makedirs(out_dir, exist_ok=True)
    cv2.imwrite(os.path.join(out_dir, f'aruco_marker_{marker_id}.png'), marker_bgr)

    gray = cv2.cvtColor(marker_bgr, cv2.COLOR_BGR2GRAY)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dict, params)
    corners, ids, _ = detector.detectMarkers(gray)
    status = f'DETECTADO ID {ids.flatten()[0]}' if ids is not None else 'FALLA'
    print(f'Marker {marker_id}: {status} ({size}x{size})')

print('Listo - marcadores con borde blanco')
