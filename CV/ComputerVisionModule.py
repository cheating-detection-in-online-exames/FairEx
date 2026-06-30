# cv_service.py  –  lag-optimised version (all bugs fixed)
from flask import Flask, request, jsonify
import cv2
import numpy as np
import mediapipe as mp
import time
import threading
from datetime import datetime
import os
import csv
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from ObjectDetection import get_landmarks, refine_label
from EyeTracking import get_iris_center, gaze_ratio, eye_aspect_ratio
from PoseEstimation import CheatingDetector
from ultralytics import YOLO

app = Flask(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SUSPICIOUS_THRESHOLD = 2
EAR_THRESHOLD        = 0.12
LEFT_EYE   = [33, 160, 158, 133, 153, 144]
RIGHT_EYE  = [362, 385, 387, 263, 373, 380]
LEFT_IRIS  = [468, 469, 470, 471]
RIGHT_IRIS = [473, 474, 475, 476]

FORBIDDEN = ["mobile", "book", "watch", "headphones", "sunglass",
             "earbuds", "laptop", "face_mask", "calculator"]

SUNGLASS_THRESHOLD   = 0.60
FACE_MASK_THRESHOLD  = 0.66
EARBUDS_THRESHOLD    = 0.50
HEADPHONES_THRESHOLD = 0.64
WATCH_THRESHOLD      = 0.27
BOOK_THRESHOLD      = 0.55
laptop_THRESHOLD     = 0.55
DEFAULT_THRESHOLD    = 0.50
DELAY_SECONDS        = 0.88
SUNGLASS_DELAY       = 1.1

# ── Performance tuning ────────────────────────────────────────────────────────
INFERENCE_WIDTH    = 480          # resize to this width before YOLO + MediaPipe
_io_executor       = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cv_io")
CSV_FLUSH_INTERVAL = 5            # flush CSV buffer every N rows

SESSION_TTL = 600                 # idle timeout in seconds

# ── Beep alert (Windows only) ─────────────────────────────────────────────────
try:
    import winsound
    MAX_BEEPS  = 3
    BEEP_COUNT = 0
    def play_beep():
        global BEEP_COUNT
        if BEEP_COUNT >= MAX_BEEPS:
            return
        winsound.Beep(1000, 300)
        BEEP_COUNT += 1
except Exception:
    BEEP_COUNT = 0
    MAX_BEEPS  = 3
    def play_beep():
        global BEEP_COUNT
        if BEEP_COUNT >= MAX_BEEPS:
            return
        print("\a")
        BEEP_COUNT += 1

# ── Load YOLO models once at startup ─────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
model      = YOLO(os.path.join(BASE_DIR, "NewFullDataSet_FT.pt"))
yolo_model = YOLO("yolov8n.pt")

cv2.setUseOptimized(True)
cv2.setNumThreads(4)

# ── Per-student sessions ──────────────────────────────────────────────────────
sessions      = {}
sessions_lock = threading.Lock()

# ── Cleanup timer ─────────────────────────────────────────────────────────────
_last_cleanup     = time.time()
_CLEANUP_INTERVAL = 60            # seconds between cleanup passes


def _maybe_cleanup():
    """Run cleanup at most once per _CLEANUP_INTERVAL to avoid per-frame overhead."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    to_delete = []
    with sessions_lock:
        for sid, s in sessions.items():
            if now - s["last_active"] > SESSION_TTL:
                to_delete.append(sid)
        for sid in to_delete:
            _close_session_locked(sid)


def _close_session_locked(sid):
    """
    Close and remove a session.
    Must be called with sessions_lock held.
    FIX: flush CSV BEFORE closing the file handle; also close face_mesh + pose_for_od.
    """
    s = sessions.pop(sid, None)
    if s is None:
        return
    # Flush remaining CSV rows BEFORE closing the file
    try:
        _flush_csv_rows(s)
    except Exception:
        pass
    # Close all MediaPipe and file resources
    for key in ("csv_file", "pose_mp", "hands_mp", "face_mesh", "pose_for_od"):
        try:
            s[key].close()
        except Exception:
            pass


def get_session(sid, exam_id="unknown", allowed_objects=None):
    """Return existing session or create a fresh one for this student."""
    _maybe_cleanup()

    with sessions_lock:
        if sid not in sessions:
            ts              = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            evidence_folder = f"evidence_{sid}_{exam_id}"
            os.makedirs(evidence_folder, exist_ok=True)

            report_path = f"{evidence_folder}/report.csv"
            with open(report_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "Time", "Violation", "Violation_Probability",
                    "Gaze_Direction", "duration_seconds",
                    "Hand_Sign", "Extra_Person", "Out_Frame", "leaning"
                ])

            pose_mp, hands_mp = _init_pose_hands()

            face_mesh_local = mp.solutions.face_mesh.FaceMesh(
                refine_landmarks=True, max_num_faces=1
            )

            pose_for_od = mp.solutions.pose.Pose(
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )

            effective_forbidden = set(FORBIDDEN) - set(allowed_objects or [])

            sessions[sid] = {
                "evidence_folder":  evidence_folder,
                "report_path":      report_path,
                "forbidden":        effective_forbidden,
                "csv_file":         open(report_path, "a", newline="", encoding="utf-8"),
                # FIX: csv_row_count resets on flush so the modulo trigger fires correctly
                "csv_pending_rows": [],
                "csv_row_count":    0,
                "last_gaze":        "Center",
                "gaze_start_time":  time.time(),
                "image_taken":      False,
                "detect_timer":     {},
                "object_active":    {},
                "best_detection":   {},
                "detector":         CheatingDetector(evidence_folder),
                "pose_mp":          pose_mp,
                "hands_mp":         hands_mp,
                "face_mesh":        face_mesh_local,
                "pose_for_od":      pose_for_od,
                "last_active":      time.time(),
            }

        sessions[sid]["last_active"] = time.time()
        return sessions[sid]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _init_pose_hands():
    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    hands = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    return pose, hands


def _resize_for_inference(frame):
    """
    Downscale frame to INFERENCE_WIDTH while preserving aspect ratio.
    Returns (small_frame, scale_x, scale_y) so bounding boxes can be
    mapped back to the original resolution if needed.
    """
    h, w = frame.shape[:2]
    if w <= INFERENCE_WIDTH:
        return frame, 1.0, 1.0
    scale = INFERENCE_WIDTH / w
    new_w = int(w * scale)
    new_h = int(h * scale)
    small = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return small, 1.0 / scale, 1.0 / scale


def _save_image_async(path, frame):
    """Write image to disk in background thread — never blocks the response."""
    _io_executor.submit(cv2.imwrite, path, frame)


def _delete_file_async(path):
    """
    FIX: delete old evidence images in background thread so os.remove()
    never blocks the main response thread.
    """
    def _do_delete(p):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    _io_executor.submit(_do_delete, path)


def _flush_csv_rows(s):
    """
    Write all pending CSV rows to disk and flush the file handle.
    FIX: reset csv_row_count to 0 after flush so the modulo trigger
    in _append_csv_row fires correctly on subsequent rows.
    """
    rows = s["csv_pending_rows"]
    if not rows:
        return
    writer = csv.writer(s["csv_file"])
    for row in rows:
        writer.writerow(row)
    s["csv_file"].flush()
    s["csv_pending_rows"].clear()
    s["csv_row_count"] = 0        # FIX: reset so next flush triggers at interval N


def _append_csv_row(s, row):
    """Buffer a CSV row; flush when buffer reaches CSV_FLUSH_INTERVAL."""
    s["csv_pending_rows"].append(row)
    s["csv_row_count"] += 1
    if s["csv_row_count"] % CSV_FLUSH_INTERVAL == 0:
        _flush_csv_rows(s)


def process_pose_frame(frame, detector, pose, hands, evidence_folder):
    rgb           = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results_pose  = pose.process(rgb)
    results_hands = hands.process(rgb)

    violation_types, violation_messages = detector.evaluate_frame(frame, results_pose)

    sign, conf = detector.classify_hand_sign_rule_based(frame, results_hands)

    explicit_sign = (sign, conf) if sign is not None else None
    detector.update_events(violation_types, violation_messages, frame, explicit_sign=explicit_sign)

    hand_sign_present = "yes" if (sign is not None or "explicit_hand_sign" in violation_types) else "no"
    return violation_types, violation_messages, results_pose, hand_sign_present


# ── Main analysis endpoint ────────────────────────────────────────────────────
@app.route('/analyze_frame', methods=['POST'])
def analyze_frame():
    student_id      = request.form.get("student_id", "unknown")
    exam_id         = request.form.get("exam_id", "unknown")
    allowed_raw     = request.form.get("allowed_objects", "")
    allowed_objects = [o.strip() for o in allowed_raw.split(",") if o.strip()]
    file            = request.files.get("frame")
    if not file:
        return jsonify({"error": "no frame"}), 400

    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "bad image"}), 400

    s               = get_session(student_id, exam_id, allowed_objects)
    evidence_folder = s["evidence_folder"]
    detect_timer    = s["detect_timer"]
    object_active   = s["object_active"]
    best_detection  = s["best_detection"]

    result = {
        "violations":    [],
        "gaze":          "",
        "gaze_duration": 0,
        "hand_sign":     False,
        "extra_person":  False,
        "out_of_frame":  False,
        "leaning":       False,
    }

    # ── Downscale once; share across YOLO + MediaPipe ─────────────────────────
    small_frame, sx, sy = _resize_for_inference(frame)
    small_rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # ── Object Detection ──────────────────────────────────────────────────────
    pose_result  = s["pose_for_od"].process(small_rgb)
    wrists, ears = get_landmarks(small_frame, pose_result)
    yolo_results = model(small_frame)

    current_detected      = set()
    frame_detections      = {}
    current_detected_obj  = None
    violation_probability = None

    for box in yolo_results[0].boxes:
        cls   = int(box.cls[0])
        label = model.names[cls].lower().strip()
        conf  = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        refined_label = refine_label(label, conf, (cx, cy), wrists, ears)
        if refined_label not in s["forbidden"]:
            continue

        current_detected.add(refined_label)

        adjusted_threshold = {
            "sunglass":   SUNGLASS_THRESHOLD,
            "earbuds":    EARBUDS_THRESHOLD,
            "headphones": HEADPHONES_THRESHOLD,
            "watch":      WATCH_THRESHOLD,
            "face_mask":  FACE_MASK_THRESHOLD,
            "laptop":     laptop_THRESHOLD,
        }.get(refined_label, DEFAULT_THRESHOLD)

        if refined_label in ["watch", "book", "headphones", "calculator",
                              "earbuds", "laptop", "mobile"] \
                and conf >= adjusted_threshold:
            frame_detections[refined_label] = conf

            if not object_active.get(refined_label, False):
                object_active[refined_label] = True

            # Draw on original-resolution frame (scale coords back)
            ox1, oy1 = int(x1 * sx), int(y1 * sy)
            ox2, oy2 = int(x2 * sx), int(y2 * sy)
            cv2.rectangle(frame, (ox1, oy1), (ox2, oy2), (0, 0, 255), 2)
            cv2.putText(frame, f"{refined_label} {conf:.2f}", (ox1, oy1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # FIX: old evidence file deleted asynchronously (non-blocking)
            if refined_label not in best_detection or conf > best_detection[refined_label][0]:
                old = best_detection.get(refined_label, (None, None))[1]
                if old:
                    _delete_file_async(old)                  # ← async delete
                filename = f"{evidence_folder}/{refined_label}_{conf}.jpg"
                _save_image_async(filename, frame.copy())    # ← async write
                best_detection[refined_label] = (conf, filename)
            continue

        # ── Delay detect ──────────────────────────────────────────────────────
        effective_delay = SUNGLASS_DELAY if refined_label == "sunglass" else DELAY_SECONDS

        if conf >= adjusted_threshold or (label != refined_label):
            if refined_label not in detect_timer:
                detect_timer[refined_label] = time.time()
            else:
                ox1, oy1 = int(x1 * sx), int(y1 * sy)
                ox2, oy2 = int(x2 * sx), int(y2 * sy)
                cv2.rectangle(frame, (ox1, oy1), (ox2, oy2), (0, 0, 255), 2)
                cv2.putText(frame, f"{refined_label} {conf:.2f}", (ox1, oy1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                if (time.time() - detect_timer[refined_label]) >= effective_delay:
                    frame_detections[refined_label] = conf
                    if not object_active.get(refined_label, False):
                        object_active[refined_label] = True

                    # FIX: old evidence file deleted asynchronously (non-blocking)
                    if refined_label not in best_detection or conf > best_detection[refined_label][0]:
                        old = best_detection.get(refined_label, (None, None))[1]
                        if old:
                            _delete_file_async(old)                  # ← async delete
                        filename = f"{evidence_folder}/{refined_label}_{conf}.jpg"
                        _save_image_async(filename, frame.copy())    # ← async write
                        best_detection[refined_label] = (conf, filename)

                    current_detected_obj  = refined_label
                    violation_probability = conf
        else:
            detect_timer.pop(refined_label, None)

    if frame_detections:
        for obj, c in frame_detections.items():
            result["violations"].append({"object": obj, "confidence": round(c, 2)})

    for obj in list(object_active.keys()):
        if obj not in current_detected:
            object_active[obj] = False

    for obj in list(detect_timer.keys()):
        if obj not in current_detected:
            detect_timer.pop(obj, None)

    # ── Eye / Gaze Tracking ───────────────────────────────────────────────────
    face_results = s["face_mesh"].process(small_rgb)

    # FIX: initialise to "" not "Unknown" so stale gaze never pollutes CSV rows
    suspicious_gaze  = ""
    duration_seconds = 0

    if face_results.multi_face_landmarks:
        h_s, w_s = small_frame.shape[:2]
        lm = face_results.multi_face_landmarks[0].landmark

        left_iris  = get_iris_center(lm, LEFT_IRIS,  w_s, h_s)
        right_iris = get_iris_center(lm, RIGHT_IRIS, w_s, h_s)

        L_l = np.array([lm[33].x  * w_s, lm[33].y  * h_s])
        L_r = np.array([lm[133].x * w_s, lm[133].y * h_s])
        R_l = np.array([lm[362].x * w_s, lm[362].y * h_s])
        R_r = np.array([lm[263].x * w_s, lm[263].y * h_s])

        ratio = (gaze_ratio(left_iris, L_l, L_r) + gaze_ratio(right_iris, R_l, R_r)) / 2
        gaze  = "Right" if ratio < 0.40 else ("Left" if ratio > 0.60 else "Center")

        if gaze != s["last_gaze"]:
            s["last_gaze"]       = gaze
            s["gaze_start_time"] = time.time()
            s["image_taken"]     = False

        gaze_duration = time.time() - s["gaze_start_time"]

        if gaze in ["Left", "Right"] and gaze_duration >= SUSPICIOUS_THRESHOLD:
            suspicious_gaze  = gaze
            duration_seconds = round(gaze_duration, 2)
            result["gaze"]          = gaze
            result["gaze_duration"] = duration_seconds
            if not s["image_taken"]:
                s["image_taken"] = True
                ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                path = f"{evidence_folder}/suspicious_{gaze}_{ts}.jpg"
                _save_image_async(path, frame.copy())        # ← async write

    # ── Pose Estimation ───────────────────────────────────────────────────────
    frame_flipped = cv2.flip(small_frame, 1)
    violation_types, violation_messages, results_pose, hand_sign_present = process_pose_frame(
        frame_flipped, s["detector"], s["pose_mp"], s["hands_mp"], evidence_folder
    )

    out_frame    = "Yes" if "out_of_frame"   in violation_types else ""
    hand_sign    = "Yes" if hand_sign_present == "yes"          else ""
    extra_person = "Yes" if "extra_person"   in violation_types else ""
    leaning      = "Yes" if "leaning"        in violation_types else ""

    result["hand_sign"]    = hand_sign    == "Yes"
    result["extra_person"] = extra_person == "Yes"
    result["out_of_frame"] = out_frame    == "Yes"
    result["leaning"]      = leaning      == "Yes"

    # ── Write CSV (buffered) - BEST FIX ──────────────────────────────────────────
    ts_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    has_gaze_violation = suspicious_gaze in ["Left", "Right"]
    has_hand_sign = hand_sign == "Yes"
    has_extra_person = extra_person == "Yes"
    has_out_of_frame = out_frame == "Yes"
    has_leaning = leaning == "Yes"

    # Write if ANY violation exists
    if frame_detections or has_gaze_violation or has_hand_sign or has_extra_person or has_out_of_frame or has_leaning:
        if frame_detections:
            # Write one row per detected object
            for obj, c in frame_detections.items():
                _append_csv_row(s, [
                    ts_now, obj, f"{c:.2f}",
                    suspicious_gaze if has_gaze_violation else "",
                    duration_seconds if has_gaze_violation else 0,
                    hand_sign, extra_person, out_frame, leaning
                ])
        else:
            # Write single row for non-object violations
            _append_csv_row(s, [
                ts_now, "", "",
                suspicious_gaze if has_gaze_violation else "",
                duration_seconds if has_gaze_violation else 0,
                hand_sign, extra_person, out_frame, leaning
            ])
    return jsonify(result)


# ── End session endpoint ──────────────────────────────────────────────────────
@app.route('/end_session', methods=['POST'])
def end_session():
    """
    Call this from the frontend when the exam ends.
    Forces a final flush of any buffered CSV rows before closing resources.
    """
    student_id = request.form.get("student_id", "unknown")
    print(f"[end_session] called for student={student_id}")

    with sessions_lock:
        if student_id in sessions:
            s = sessions[student_id]
            pending = len(s["csv_pending_rows"])
            print(f"[end_session] flushing {pending} buffered row(s)")
            _flush_csv_rows(s)
            for key in ("csv_file", "pose_mp", "hands_mp", "face_mesh", "pose_for_od"):
                try:
                    s[key].close()
                except Exception:
                    pass
            del sessions[student_id]
        else:
            print(f"[end_session] no active session found for student={student_id}")


    return jsonify({"status": "session ended"})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False)