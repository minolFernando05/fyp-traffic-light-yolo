from ultralytics import YOLO
import cv2
import numpy as np
import psutil
import time
from pathlib import Path

# ===================== PATHS =====================
REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_PATH = REPO_ROOT / "week1" / "videos" / "traffic_2.mp4"
MODEL_PATH = REPO_ROOT / "week1" / "yolov8n.pt"

# ===================== CONFIG =====================
IMGSZ = 640
CONF = 0.35  # confidence threshold -defualt 0.35
TARGET_FPS = 15

VEHICLE_LABELS = {"car", "motorcycle", "bus", "truck"}

# 🔴 ADJUST THESE POINTS USING MOUSE COORDINATES
# Format: (x, y) clockwise
ROI_POLY = [
    (450, 360),   # top-left
    (750, 360),   # top-right
    (710, 720),  # bottom-right
    (200, 720)    # bottom-left
]

# =================================================


# ---------- Mouse helper (for ROI tuning) ----------
mouse_x, mouse_y = 0, 0
def mouse_move(event, x, y, flags, param):
    global mouse_x, mouse_y
    if event == cv2.EVENT_MOUSEMOVE:
        mouse_x, mouse_y = x, y


# ---------- Geometry helpers ----------
def create_roi_mask(frame_shape, polygon):
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask

def point_in_polygon(cx, cy, polygon):
    poly_np = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(poly_np, (cx, cy), False) >= 0


# ===================== MAIN =====================
def main():
    print("Loading model...")
    model = YOLO(str(MODEL_PATH))

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video")

    ret, frame0 = cap.read()
    if not ret:
        raise RuntimeError("Cannot read first frame")

    roi_mask = create_roi_mask(frame0.shape, ROI_POLY)

    frame_interval = 1.0 / TARGET_FPS
    last_frame_time = time.time()

    cv2.namedWindow("Trapezium ROI - Edge YOLO")
    cv2.setMouseCallback("Trapezium ROI - Edge YOLO", mouse_move)

    print("Running... Press Q to quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # FPS throttle
        now = time.time()
        elapsed = now - last_frame_time
        if elapsed < frame_interval:
            time.sleep(frame_interval - elapsed)
        last_frame_time = time.time()

        # Masked frame (visual only)
        masked_frame = cv2.bitwise_and(frame, frame, mask=roi_mask)

        # YOLO inference
        t0 = time.time()
        results = model.predict(
            source=frame,
            imgsz=IMGSZ,
            conf=CONF,
            verbose=False
        )[0]
        infer_ms = (time.time() - t0) * 1000

        vehicle_count = 0

        if results.boxes is not None:
            for box in results.boxes:
                cls_id = int(box.cls[0])
                label = results.names[cls_id]

                if label not in VEHICLE_LABELS:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # 🔑 Only vehicles INSIDE trapezium
                if point_in_polygon(cx, cy, ROI_POLY):
                    vehicle_count += 1
                    cv2.rectangle(frame, (x1, y1), (x2, y2),
                                (0, 0, 255), 2)
                    cv2.putText(frame, label, (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (0, 0, 255), 2)

        # Draw trapezium ROI
        roi_pts = np.array(ROI_POLY, np.int32)
        cv2.polylines(frame, [roi_pts], True, (0, 255, 0), 2)
        cv2.putText(frame, "ROI", ROI_POLY[0],
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (0, 255, 0), 2)

        # Metrics
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        cv2.putText(frame, f"Vehicles in ROI: {vehicle_count}", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
        cv2.putText(frame, f"Infer: {infer_ms:.1f} ms | CPU: {cpu:.0f}% | MEM: {mem:.0f}%",
                    (30, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (255, 255, 255), 2)
        cv2.putText(frame, f"Mouse x={mouse_x}, y={mouse_y}", (30, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 255, 255), 2)

        cv2.imshow("Trapezium ROI - Edge YOLO", frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Stopped.")


if __name__ == "__main__":
    main()
