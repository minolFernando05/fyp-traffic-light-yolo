import os
import time
import json
import csv
from pathlib import Path

import cv2
import psutil
from ultralytics import YOLO

# ----------------- CONFIG -----------------
# If you run from repo root, these paths are correct.
REPO_ROOT = Path(__file__).resolve().parents[2]

VIDEO_PATH = REPO_ROOT / "week1" / "videos" / "traffic_2.mp4"
MODEL_PATH = REPO_ROOT / "week1" / "yolov8n.pt"

IMGSZ = 640
CONF = 0.35
TARGET_FPS = 15
LOG_EVERY_N_FRAMES = 1  # keep 1 for detailed logs; set 5 to reduce CSV size

# Output files
OUT_CSV = REPO_ROOT / "week4" / "metrics" / "edge_metrics.csv"
OUT_JSON = REPO_ROOT / "week4" / "integration" / "live_counts.json"

# COCO classes we care about
VEHICLE_LABELS = {"car", "motorcycle", "bus", "truck"}

# Emergency detection placeholder (Week 4 demo: keep false unless you have a model/class)
# Later you can set this true if ambulance detected.
ENABLE_EMERGENCY = False
EMERGENCY_LABELS = {"ambulance"}  # if you train/use a model with this class

# ROI definition strategy:
# Since you have a "vehicles coming towards intersection" video, start with ONE ROI near stop-line.
# We'll define ROI after reading first frame. Adjust STOPLINE_ROI manually after first run.
STOPLINE_ROI = None  # set after first frame as (x1,y1,x2,y2)
# ------------------------------------------


def point_in_rect(cx, cy, rect):
    x1, y1, x2, y2 = rect
    return x1 <= cx <= x2 and y1 <= cy <= y2


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def get_cpu_mem():
    # cpu_percent(None) gives % since last call; that's fine for per-frame logging
    return psutil.cpu_percent(interval=None), psutil.virtual_memory().percent


def main():
    if not VIDEO_PATH.exists():
        raise RuntimeError(f"Video not found: {VIDEO_PATH}")
    if not MODEL_PATH.exists():
        raise RuntimeError(f"Model not found: {MODEL_PATH}")

    model = YOLO(str(MODEL_PATH))
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {VIDEO_PATH}")

    # Read first frame to size ROIs
    ret, frame0 = cap.read()
    if not ret:
        raise RuntimeError("Could not read first frame.")
    h, w = frame0.shape[:2]

    global STOPLINE_ROI
    if STOPLINE_ROI is None:
        # Default: bottom-middle region (common stop-line area for forward-facing videos)
        # You MUST adjust after you see the green rectangle on-screen.
        # STOPLINE_ROI = (int(w * 0.10), int(h * 0.40), int(w * 0.35), int(h * 0.95))
        STOPLINE_ROI = (232,230,775,1000)

    ROIS = {"Approach": STOPLINE_ROI}

    # restart video
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    ensure_parent(OUT_CSV)
    ensure_parent(OUT_JSON)

    # Prepare CSV
    write_header = not OUT_CSV.exists()
    csv_f = open(OUT_CSV, "a", newline="")
    writer = csv.writer(csv_f)
    if write_header:
        writer.writerow([
            "frame_idx", "sim_time_sec",
            "inference_ms", "loop_ms", "target_fps",
            "cpu_percent", "mem_percent",
            "vehicle_count", "emergency_detected"
        ])

    frame_idx = 0
    start_wall = time.time()
    last_frame_wall = time.time()
    frame_interval = 1.0 / TARGET_FPS

    # Warm-up CPU percent
    psutil.cpu_percent(interval=None)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # FPS throttle
        now = time.time()
        elapsed = now - last_frame_wall
        if elapsed < frame_interval:
            time.sleep(frame_interval - elapsed)
        last_frame_wall = time.time()

        loop_t0 = time.time()

        # Crop ROI to reduce compute
        x1, y1, x2, y2 = ROIS["Approach"]
        roi_frame = frame[y1:y2, x1:x2]

        # YOLO inference timing
        t0 = time.time()
        results = model.predict(
            source=roi_frame,
            imgsz=IMGSZ,
            conf=CONF,
            verbose=False
        )[0]
        inference_ms = (time.time() - t0) * 1000.0

        # Count vehicles by center point (in ROI coords)
        vehicle_count = 0
        emergency_detected = False

        if results.boxes is not None and len(results.boxes) > 0:
            for box in results.boxes:
                cls_id = int(box.cls[0])
                label = results.names.get(cls_id, str(cls_id))

                # Emergency demo (optional)
                if ENABLE_EMERGENCY and label in EMERGENCY_LABELS:
                    emergency_detected = True

                if label not in VEHICLE_LABELS:
                    continue

                # Boxes are in ROI coordinate space
                bx1, by1, bx2, by2 = box.xyxy[0]
                cx = int((bx1 + bx2) / 2)
                cy = int((by1 + by2) / 2)

                # Since boxes are already from roi_frame, we just check inside ROI frame bounds:
                if 0 <= cx <= (x2 - x1) and 0 <= cy <= (y2 - y1):
                    vehicle_count += 1

        cpu, mem = get_cpu_mem()
        sim_time = time.time() - start_wall
        loop_ms = (time.time() - loop_t0) * 1000.0

        # Write integration JSON (controller will read this)
        payload = {
            "t": round(sim_time, 3),
            "counts": {
                "Approach": int(vehicle_count)
            },
            "emergency": bool(emergency_detected)
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2))

        # Write CSV metrics
        if frame_idx % LOG_EVERY_N_FRAMES == 0:
            writer.writerow([
                frame_idx, round(sim_time, 3),
                round(inference_ms, 2), round(loop_ms, 2), TARGET_FPS,
                round(cpu, 1), round(mem, 1),
                int(vehicle_count), int(emergency_detected)
            ])
            csv_f.flush()

        # Draw ROI on full frame for tuning
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, "ROI: Approach", (x1 + 10, y1 + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        cv2.putText(frame, f"Count: {vehicle_count}", (30, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
        cv2.putText(frame, f"Infer: {inference_ms:.1f} ms | CPU: {cpu:.0f}% | MEM: {mem:.0f}%",
                    (30, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(frame, f"Target FPS: {TARGET_FPS}", (30, 125),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

        cv2.imshow("Week4 Edge Metrics", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        frame_idx += 1

    cap.release()
    csv_f.close()
    cv2.destroyAllWindows()

    print("Done.")
    print("Metrics CSV:", OUT_CSV)
    print("Live counts JSON:", OUT_JSON)


if __name__ == "__main__":
    main()
