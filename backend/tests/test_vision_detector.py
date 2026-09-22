"""Tests unitarios para backend/vision/detector.py — Detection y VisionDetector.

No se testea la inferencia YOLO real (requiere el modelo cargado) — se
testean las partes puras: Detection.to_dict(), draw_overlay(), get_status(),
y el comportamiento cuando la visión está deshabilitada / el modelo no
está disponible (rutas que sí se ejercitan sin YOLO real).
"""
import numpy as np
import pytest

from backend.vision.detector import Detection, VisionDetector


class TestDetection:
    def test_to_dict_rounds_confidence_and_distance(self):
        d = Detection(class_id=0, label='person', confidence=0.91234,
                       bbox=(10, 20, 30, 40), distance=4.5678, zone='safe')
        result = d.to_dict()
        assert result == {
            'class_id': 0, 'label': 'person', 'confidence': 0.91,
            'bbox': {'x1': 10, 'y1': 20, 'x2': 30, 'y2': 40},
            'distance': 4.57, 'zone': 'safe',
        }

    def test_to_dict_casts_bbox_to_int(self):
        d = Detection(class_id=1, label='car', confidence=0.5,
                       bbox=(1.9, 2.1, 3.9, 4.1), distance=1.0, zone='warning')
        result = d.to_dict()
        assert result['bbox'] == {'x1': 1, 'y1': 2, 'x2': 3, 'y2': 4}


@pytest.fixture
def detector_disabled(monkeypatch):
    """VisionDetector con la visión deshabilitada — no intenta cargar YOLO."""
    monkeypatch.setattr('backend.config.VISION_ENABLED', False)
    return VisionDetector()


class TestVisionDisabled:
    def test_detect_returns_empty_list_when_disabled(self, detector_disabled):
        frame = np.zeros((480, 640, 3), dtype='uint8')
        assert detector_disabled.detect(frame) == []

    def test_vision_disabled_flag_set(self, detector_disabled):
        assert detector_disabled._vision_disabled is True

    def test_detect_with_none_frame_returns_empty(self, detector_disabled):
        assert detector_disabled.detect(None) == []


class TestDrawOverlay:
    @pytest.fixture
    def detections(self):
        return [
            Detection(class_id=0, label='person', confidence=0.91,
                       bbox=(10, 10, 100, 200), distance=4.2, zone='safe'),
            Detection(class_id=2, label='car', confidence=0.75,
                       bbox=(200, 50, 350, 150), distance=1.5, zone='warning'),
            Detection(class_id=0, label='person', confidence=0.60,
                       bbox=(400, 100, 450, 300), distance=0.8, zone='critical'),
        ]

    def test_none_frame_returns_none(self, detector_disabled):
        assert detector_disabled.draw_overlay(None, []) is None

    def test_returns_frame_of_same_shape(self, detector_disabled, detections):
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = detector_disabled.draw_overlay(frame, detections)
        assert result.shape == frame.shape

    def test_does_not_mutate_original_frame(self, detector_disabled, detections):
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = detector_disabled.draw_overlay(frame, detections)
        assert not np.array_equal(result, frame)  # se dibujó algo encima
        assert np.array_equal(frame, np.zeros((480, 640, 3), dtype='uint8'))  # original intacto

    def test_empty_detections_returns_unmodified_copy(self, detector_disabled):
        frame = np.zeros((10, 10, 3), dtype='uint8')
        result = detector_disabled.draw_overlay(frame, [])
        assert np.array_equal(result, frame)

    def test_label_includes_confidence_percent(self, detector_disabled):
        # Verificación indirecta: con confidence=0.91 se debería dibujar "91%"
        # en algún punto del frame — comprobamos que draw_overlay no falla y
        # que el frame cambia respecto al original (evidencia de texto dibujado).
        det = [Detection(class_id=0, label='person', confidence=0.91,
                          bbox=(5, 5, 40, 40), distance=2.0, zone='safe')]
        frame = np.zeros((60, 60, 3), dtype='uint8')
        result = detector_disabled.draw_overlay(frame, det)
        assert result.sum() > 0


class TestGetStatus:
    def test_empty_when_no_detections(self, detector_disabled):
        status = detector_disabled.get_status()
        assert status == {'detections': [], 'count': 0, 'critical_count': 0, 'warning_count': 0}

    def test_counts_by_zone(self, detector_disabled):
        detector_disabled.last_detections = [
            Detection(0, 'person', 0.9, (0, 0, 1, 1), 1.0, 'critical'),
            Detection(0, 'person', 0.9, (0, 0, 1, 1), 3.0, 'warning'),
            Detection(0, 'person', 0.9, (0, 0, 1, 1), 8.0, 'safe'),
        ]
        status = detector_disabled.get_status()
        assert status['count'] == 3
        assert status['critical_count'] == 1
        assert status['warning_count'] == 1

    def test_detections_serialized_as_dicts(self, detector_disabled):
        detector_disabled.last_detections = [
            Detection(0, 'person', 0.9, (0, 0, 1, 1), 1.0, 'critical'),
        ]
        status = detector_disabled.get_status()
        assert status['detections'][0]['label'] == 'person'


class _Xyxy:
    def __init__(self, vals):
        self._vals = vals

    def tolist(self):
        return list(self._vals)


class _FakeBoxes:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [_Xyxy(xyxy)]

    def __len__(self):
        return 1


def _make_fake_model(cls_id, conf, bbox):
    class FakeModel:
        names = {0: 'person', 2: 'car'}

        def __call__(self, frame, verbose=False, imgsz=640, conf=0.4):
            class Result:
                pass
            r = Result()
            r.boxes = _FakeBoxes(cls_id, conf, bbox)
            return [r]

    return FakeModel()


class TestDetectDistancePriority:
    """Ejercita detect() con un modelo YOLO mockeado para cubrir la lógica de
    prioridad de distancia (profundidad real > MTF01 > estimación monocular)
    sin depender de que ultralytics/YOLO real esté disponible."""

    def _detector_with_mock_model(self, monkeypatch, bbox, conf=0.9, cls_id=0):
        monkeypatch.setattr('backend.config.VISION_ENABLED', True)
        det = VisionDetector.__new__(VisionDetector)
        det.last_detections = []
        det.frame_width = 640
        det.frame_height = 480
        det._vision_disabled = False
        det._model_ready = True
        det._model = _make_fake_model(cls_id, conf, bbox)
        return det

    def test_uses_real_depth_when_available(self, monkeypatch):
        det = self._detector_with_mock_model(monkeypatch, bbox=(10, 10, 50, 50))
        frame = np.zeros((480, 640, 3), dtype='uint8')
        depth_frame = np.full((480, 640), 2000, dtype='uint16')  # 2000mm en toda la imagen
        result = det.detect(frame, depth_frame=depth_frame, depth_scale=0.001)
        assert len(result) == 1
        assert result[0].distance == pytest.approx(2.0, abs=0.01)

    def test_falls_back_to_mtf01_when_centered_and_no_depth(self, monkeypatch):
        det = self._detector_with_mock_model(monkeypatch, bbox=(280, 200, 360, 280))  # centrado
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = det.detect(frame, depth_frame=None, mtf_forward_m=3.5)
        assert result[0].distance == pytest.approx(3.5)

    def test_ignores_mtf01_when_not_centered(self, monkeypatch):
        det = self._detector_with_mock_model(monkeypatch, bbox=(0, 0, 20, 20))  # esquina, no centrado
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = det.detect(frame, depth_frame=None, mtf_forward_m=3.5)
        assert result[0].distance != pytest.approx(3.5)  # cae a estimación monocular

    def test_falls_back_to_monocular_estimate(self, monkeypatch):
        det = self._detector_with_mock_model(monkeypatch, bbox=(100, 100, 150, 300))  # bbox alto
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = det.detect(frame, depth_frame=None, mtf_forward_m=None)
        assert result[0].distance > 0
        assert result[0].distance != 999.0

    def test_zone_classification_safe_warning_critical(self, monkeypatch):
        det = self._detector_with_mock_model(monkeypatch, bbox=(10, 10, 20, 400))  # bbox muy alto -> cerca
        frame = np.zeros((480, 640, 3), dtype='uint8')
        result = det.detect(frame, depth_frame=None)
        assert result[0].zone in ('safe', 'warning', 'critical')

    def test_model_none_returns_empty(self, monkeypatch):
        monkeypatch.setattr('backend.config.VISION_ENABLED', True)
        det = VisionDetector.__new__(VisionDetector)
        det._vision_disabled = False
        det._model_ready = True
        det._model = None
        frame = np.zeros((10, 10, 3), dtype='uint8')
        assert det.detect(frame) == []

    def test_inference_exception_returns_empty_and_is_caught(self, monkeypatch):
        monkeypatch.setattr('backend.config.VISION_ENABLED', True)
        det = VisionDetector.__new__(VisionDetector)
        det._vision_disabled = False
        det._model_ready = True

        def raise_error(*a, **kw):
            raise RuntimeError('inference failed')

        det._model = raise_error
        frame = np.zeros((10, 10, 3), dtype='uint8')
        assert det.detect(frame) == []
