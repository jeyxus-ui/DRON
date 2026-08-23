import cv2
import numpy as np
import logging
import math
import threading

logger = logging.getLogger(__name__)

FOCAL_LENGTH_ESTIMATE = 184.0
SAFE_DISTANCE_M = 5.0
WARNING_DISTANCE_M = 2.0

KNOWN_HEIGHTS = {
    0: 1.7,    # person
    1: 1.7,    # bicycle
    2: 1.5,    # car
    3: 1.2,    # motorcycle
    5: 0.6,    # bus (height)
    6: 1.5,    # train
    7: 1.5,    # truck
    9: 0.5,    # traffic light
    11: 0.3,   # stop sign
    13: 0.3,   # bench
    14: 0.8,   # bird
    15: 0.4,   # cat
    16: 0.5,   # dog
    17: 0.3,   # horse
    18: 0.3,   # sheep
    19: 0.3,   # cow
    20: 0.2,   # elephant
    21: 0.5,   # bear
    22: 0.2,   # zebra
    23: 0.2,   # giraffe
    24: 0.5,   # backpack
    25: 0.5,   # umbrella
    26: 1.0,   # handbag
    27: 0.6,   # tie
    28: 0.5,   # suitcase
    29: 0.3,   # frisbee
    30: 0.2,   # skis
    31: 0.3,   # snowboard
    32: 0.5,   # sports ball
    33: 0.3,   # kite
    34: 0.5,   # baseball bat
    35: 0.3,   # baseball glove
    36: 0.3,   # skateboard
    37: 0.3,   # surfboard
    38: 0.3,   # tennis racket
    39: 0.5,   # bottle
    41: 0.2,   # cup
    42: 0.2,   # fork
    43: 0.2,   # knife
    44: 0.2,   # spoon
    45: 0.2,   # bowl
    46: 1.0,   # banana
    47: 0.1,   # apple
    48: 0.2,   # sandwich
    49: 0.2,   # orange
    50: 0.2,   # broccoli
    51: 0.2,   # carrot
    52: 0.1,   # hot dog
    53: 0.2,   # pizza
    54: 0.3,   # donut
    55: 0.2,   # cake
    56: 0.5,   # chair
    57: 0.5,   # couch
    58: 0.5,   # potted plant
    59: 0.8,   # bed
    60: 1.0,   # dining table
    61: 0.5,   # toilet
    62: 0.5,   # tv
    63: 0.5,   # laptop
    64: 0.3,   # mouse
    65: 0.3,   # remote
    66: 0.3,   # keyboard
    67: 0.2,   # cell phone
    68: 0.3,   # microwave
    69: 0.5,   # oven
    70: 0.5,   # toaster
    71: 0.5,   # sink
    72: 0.5,   # refrigerator
    73: 0.5,   # book
    74: 0.3,   # clock
    75: 0.3,   # vase
    76: 0.3,   # scissors
    77: 0.3,   # teddy bear
    78: 0.3,   # hair drier
    79: 0.3,   # toothbrush
}


class Detection:
    def __init__(self, class_id: int, label: str, confidence: float,
                 bbox, distance: float, zone: str):
        self.class_id = class_id
        self.label = label
        self.confidence = confidence
        self.bbox = bbox
        self.distance = distance
        self.zone = zone

    def to_dict(self):
        x1, y1, x2, y2 = self.bbox
        return {
            "class_id": self.class_id,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)},
            "distance": round(self.distance, 2),
            "zone": self.zone,
        }


class VisionDetector:
    def __init__(self):
        self.last_detections: list[Detection] = []
        self.frame_width = 640
        self.frame_height = 480
        self._model = None
        self._model_ready = False
        self._model_loaded = threading.Event()
        self._vision_disabled = False
        self._start_model_load()

    def _start_model_load(self):
        try:
            from backend.config import VISION_ENABLED
        except ImportError:
            VISION_ENABLED = True
        if not VISION_ENABLED:
            self._vision_disabled = True
            self._model_loaded.set()
            logger.info("Visión YOLO deshabilitada (DRON_VISION_ENABLED=0)")
            return
        try:
            from ultralytics import YOLO
            import os
            model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'models', 'yolov8n.pt')
            def _load():
                try:
                    self._model = YOLO(model_path)
                    self._model_ready = True
                    self._model_loaded.set()
                    logger.info("YOLOv8n model loaded")
                except Exception as e:
                    logger.error(f"Failed to load YOLO model: {e}")
                    self._model_loaded.set()
            t = threading.Thread(target=_load, daemon=True)
            t.start()
        except ImportError:
            logger.warning("ultralytics no instalado, detección YOLO deshabilitada")
            self._model_loaded.set()

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if frame is None or self._vision_disabled:
            return []
        if not self._model_ready:
            self._model_loaded.wait(timeout=5.0)
        if self._model is None:
            return []
        h, w = frame.shape[:2]
        self.frame_width = w
        self.frame_height = h

        try:
            results = self._model(frame, verbose=False, imgsz=640, conf=0.4)
            detections = []
            if results and len(results) > 0:
                boxes = results[0].boxes
                if boxes is not None and len(boxes) > 0:
                    for i in range(len(boxes)):
                        cls_id = int(boxes.cls[i])
                        conf = float(boxes.conf[i])
                        x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                        bbox_h = y2 - y1
                        bbox_w = x2 - x1
                        label = self._model.names[cls_id] if self._model.names else str(cls_id)
                        known_h = KNOWN_HEIGHTS.get(cls_id, 0.5)
                        distance = (known_h * FOCAL_LENGTH_ESTIMATE) / bbox_h if bbox_h > 0 else 999.0
                        if distance > SAFE_DISTANCE_M:
                            zone = "safe"
                        elif distance > WARNING_DISTANCE_M:
                            zone = "warning"
                        else:
                            zone = "critical"
                        detections.append(Detection(
                            class_id=cls_id, label=label, confidence=conf,
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            distance=distance, zone=zone,
                        ))
            self.last_detections = detections
            return detections
        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
            return []

    def draw_overlay(self, frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        if frame is None:
            return frame
        result = frame.copy()
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            if d.zone == "critical":
                color = (0, 0, 255)
            elif d.zone == "warning":
                color = (0, 165, 255)
            else:
                color = (0, 255, 0)
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            label = f"{d.label} {d.distance:.1f}m [{d.zone}]"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(result, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(result, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        return result

    def get_status(self) -> dict:
        return {
            "detections": [d.to_dict() for d in self.last_detections],
            "count": len(self.last_detections),
            "critical_count": sum(1 for d in self.last_detections if d.zone == "critical"),
            "warning_count": sum(1 for d in self.last_detections if d.zone == "warning"),
        }
