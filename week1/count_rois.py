from ultralytics import YOLO
import cv2

VIDEO_PATH = "videos/traffic_2.mp4"

# We only count these COCO classes
VEHICLE_LABELS = {"car", "motorcycle", "bus", "truck"}

def point_in_rect(cx, cy, rect):
    x1, y1, x2, y2 = rect
    return x1 <= cx <= x2 and y1 <= cy <= y2

def main():
    model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {VIDEO_PATH}")

    # Read one frame to define ROIs based on frame size
    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Could not read first frame.")
    h, w = frame.shape[:2]

    # TODO: Adjust these ROIs to match your junction lanes/approaches
    # Format: (x1, y1, x2, y2)
    ROIS = {
        "North": (0, 0, w // 2, h // 2),
        "South": (0, h // 2, w // 2, h),
        "East":  (w // 2, 0, w, h // 2),
        "West":  (w // 2, h // 2, w, h),
    }

    # Restart video
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, verbose=False)[0]
        counts = {name: 0 for name in ROIS}

        if results.boxes is not None:
            for box in results.boxes:
                cls_id = int(box.cls[0])
                label = results.names[cls_id]

                if label not in VEHICLE_LABELS:
                    continue

                x1, y1, x2, y2 = box.xyxy[0]
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                for roi_name, rect in ROIS.items():
                    if point_in_rect(cx, cy, rect):
                        counts[roi_name] += 1

        # Draw ROIs
        for roi_name, (x1, y1, x2, y2) in ROIS.items():
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, roi_name, (x1 + 10, y1 + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Overlay counts
        y = 30
        for name, c in counts.items():
            cv2.putText(frame, f"{name}: {c}", (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            y += 35

        print(counts)  # required: print counts each frame

        cv2.imshow("Counts per ROI (Per Frame)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
