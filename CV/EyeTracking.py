import cv2
import mediapipe as mp
import numpy as np
import os, csv, time
from datetime import datetime

# -------------------------
# Helper Functions
# -------------------------

def gaze_ratio(iris_center, corner_left, corner_right):
    eye_width = np.linalg.norm(corner_right - corner_left)
    iris_x = np.linalg.norm(iris_center - corner_left)
    return iris_x / eye_width


def get_iris_center(landmarks, indices, w, h):
    pts = np.array([(landmarks[i].x * w, landmarks[i].y * h) for i in indices])
    return np.mean(pts, axis=0)


def eye_aspect_ratio(eye):
    A = np.linalg.norm(eye[1] - eye[5])
    B = np.linalg.norm(eye[2] - eye[4])
    C = np.linalg.norm(eye[0] - eye[3])
    return (A + B) / (2.0 * C)


def get_head_direction(landmarks, w, h):
    nose = np.array([landmarks[1].x * w, landmarks[1].y * h])
    left_face = np.array([landmarks[234].x * w, landmarks[234].y * h])
    right_face = np.array([landmarks[454].x * w, landmarks[454].y * h])

    face_center_x = (left_face[0] + right_face[0]) / 2
    diff = nose[0] - face_center_x

    if diff > 20:
        return "Right"
    elif diff < -20:
        return "Left"
    else:
        return "Center"


# -------------------------
# Main Function
# -------------------------

def run_eye_tracking():

    gaze_folder = "gaze_screenshots"
    blink_folder = "blink_screenshots"
    report_path = "eye_tracking_report.csv"

    os.makedirs(gaze_folder, exist_ok=True)
    os.makedirs(blink_folder, exist_ok=True)

    LEFT_EYE = [33, 160, 158, 133, 153, 144]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]

    LEFT_IRIS = [468, 469, 470, 471]
    RIGHT_IRIS = [473, 474, 475, 476]

    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)

    if not os.path.exists(report_path):
        with open(report_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "Gaze", "EAR", "Blink", "Screenshot", "Suspicious"])

    last_gaze = "Center"
    gaze_start_time = time.time()
    SUSPICIOUS_THRESHOLD = 2

    # 🔥 Blink variables
    blink_start_time = None
    blink_count = 0
    LONG_BLINK_THRESHOLD = 1.5

    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        gaze = "Unknown"
        blink = False
        ear = 0
        screenshot_file = ""
        suspicious_event = "No"

        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0].landmark

            # -------------------------
            # Eye Detection
            # -------------------------
            left_eye = np.array([(lm[i].x * w, lm[i].y * h) for i in LEFT_EYE])
            right_eye = np.array([(lm[i].x * w, lm[i].y * h) for i in RIGHT_EYE])

            ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2

            # -------------------------
            # 🔥 Advanced Blink Detection
            # -------------------------
            if ear < 0.18:
                blink = True
                if blink_start_time is None:
                    blink_start_time = time.time()

            else:
                if blink_start_time is not None:
                    blink_duration = time.time() - blink_start_time
                    blink_count += 1

                    if blink_duration < LONG_BLINK_THRESHOLD:
                        screenshot_file = f"{blink_folder}/blink_{int(time.time())}.jpg"
                    else:
                        suspicious_event = "Yes"
                        screenshot_file = f"{blink_folder}/long_blink_{int(time.time())}.jpg"

                    cv2.imwrite(screenshot_file, frame)
                    blink_start_time = None

            # -------------------------
            # Eye Gaze
            # -------------------------
            left_iris_center = get_iris_center(lm, LEFT_IRIS, w, h)
            right_iris_center = get_iris_center(lm, RIGHT_IRIS, w, h)

            L_left = np.array([lm[33].x * w, lm[33].y * h])
            L_right = np.array([lm[133].x * w, lm[133].y * h])

            R_left = np.array([lm[362].x * w, lm[362].y * h])
            R_right = np.array([lm[263].x * w, lm[263].y * h])

            left_ratio = gaze_ratio(left_iris_center, L_left, L_right)
            right_ratio = gaze_ratio(right_iris_center, R_left, R_right)
            ratio = (left_ratio + right_ratio) / 2

            if ratio < 0.40:
                eye_gaze = "Right"
            elif ratio > 0.60:
                eye_gaze = "Left"
            else:
                eye_gaze = "Center"

            # -------------------------
            # Head Direction
            # -------------------------
            head_gaze = get_head_direction(lm, w, h)

            # Combine
            if eye_gaze == head_gaze:
                gaze = eye_gaze
            else:
                gaze = head_gaze

            # -------------------------
            # Suspicious Gaze
            # -------------------------
            if gaze != last_gaze:
                last_gaze = gaze
                gaze_start_time = time.time()

            gaze_duration = time.time() - gaze_start_time

            if gaze in ["Left", "Right"] and gaze_duration >= SUSPICIOUS_THRESHOLD:
                suspicious_event = "Yes"
                screenshot_file = f"{gaze_folder}/suspicious_{gaze}_{int(time.time())}.jpg"
                cv2.imwrite(screenshot_file, frame)

            elif gaze in ["Left", "Right"]:
                screenshot_file = f"{gaze_folder}/normal_{gaze}_{int(time.time())}.jpg"
                cv2.imwrite(screenshot_file, frame)

            # -------------------------
            # Save CSV
            # -------------------------
            with open(report_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    gaze,
                    f"{ear:.2f}",
                    "Yes" if blink else "No",
                    screenshot_file,
                    suspicious_event
                ])

            # -------------------------
            # Display
            # -------------------------
            cv2.putText(frame, f"Gaze: {gaze}", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.putText(frame, f"Head: {head_gaze}", (30, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            cv2.putText(frame, f"Eye: {eye_gaze}", (30, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.putText(frame, f"Blinks: {blink_count}", (30, 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            if blink:
                cv2.putText(frame, "Blinking", (30, 190),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow("Exam Eye Tracking", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    return report_path, gaze_folder, blink_folder