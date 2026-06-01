import cv2
import numpy as np

print('OpenCV:', cv2.__version__)

dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
marker = cv2.aruco.generateImageMarker(dict, 0, 200)
marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)

img = np.ones((480, 640, 3), dtype=np.uint8) * 200
img[140:340, 220:420] = marker_bgr

params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(dict, params)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
corners, ids, _ = detector.detectMarkers(gray)
print('IDs detectados:', ids.flatten() if ids is not None else 'ninguno')
if ids is not None:
    for i, id in enumerate(ids.flatten()):
        pts = corners[i][0]
        marker_pixels = max(np.linalg.norm(pts[1]-pts[0]), np.linalg.norm(pts[2]-pts[1]))
        dist = (0.15 * 600.0) / marker_pixels if marker_pixels > 0 else 999
        print(f'  ID {id}: {marker_pixels:.1f}px -> {dist:.2f}m')

import os
_aruco_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', 'markers')

for mid in [0, 1, 42]:
    path = os.path.join(_aruco_dir, f'aruco_marker_{mid}.png')
    test = cv2.imread(path)
    if test is None:
        print(f'  No se pudo leer {path}')
        continue
    # Place on larger image
    canvas = np.ones((480, 640, 3), dtype=np.uint8) * 200
    h, w = test.shape[:2]
    xo, yo = (640-w)//2, (480-h)//2
    canvas[yo:yo+h, xo:xo+w] = test
    gray2 = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    c2, ids2, _ = detector.detectMarkers(gray2)
    if ids2 is not None:
        for j, id2 in enumerate(ids2.flatten()):
            pts2 = c2[j][0]
            mp = max(np.linalg.norm(pts2[1]-pts2[0]), np.linalg.norm(pts2[2]-pts2[1]))
            d = (0.15 * 600.0) / mp if mp > 0 else 999
            print(f'  PNG {mid}: ID {id2} -> {mp:.1f}px -> {d:.2f}m')
    else:
        print(f'  PNG {mid}: no detectado')
