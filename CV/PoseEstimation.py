import cv2
import time
import math
import os
import numpy as np
# ---- Protobuf compatibility patch for Mediapipe ----
from google.protobuf import message_factory as _message_factory

if not hasattr(_message_factory, "GetMessageClass"):
    def GetMessageClass(descriptor):
        factory = _message_factory.MessageFactory()
        return factory.GetPrototype(descriptor)
    _message_factory.GetMessageClass = GetMessageClass


import mediapipe as mp
#
# # ==========================
# # MEDIAPIPE SETUP
# # ==========================
mp_pose = mp.solutions.pose
mp_hands = mp.solutions.hands

# ==========================
# HAND-SIGN CONFIG
# ==========================
TIP_IDS = [4, 8, 12, 16, 20]
CHEATING_GESTURES = {"1", "2", "3", "4"}
NON_CHEATING_GESTURES = {"0", "5"}

# ==========================
# RULE-BASED HAND-SIGN RECOGNITION
# ==========================
# ==========================
# OPTIONAL: YOLO FOR EXTRA PERSON
# ==========================
USE_YOLO = True
yolo_model = None
if USE_YOLO:
    try:
        from ultralytics import YOLO
        yolo_model = YOLO("yolov8n.pt")  # COCO model (person class = 0)
    except Exception as e:
        print("[WARN] YOLO not available, extra-person detection disabled:", e)
        yolo_model = None

# YOLO filtering thresholds to reduce false positives
EXTRA_PERSON_CONF_THRESH = 0.6      # ignore person boxes below this confidence
EXTRA_PERSON_MIN_AREA_FRAC = 0.05   # ignore tiny boxes (< 5% of frame area)


# ==========================
# SIMPLE BEEP FUNCTION
# ==========================
MAX_BEEPS = 3
BEEP_COUNT = 0

try:
    import winsound

    def play_beep():
        global BEEP_COUNT
        if BEEP_COUNT >= MAX_BEEPS:
            return
        winsound.Beep(1000, 300)
        BEEP_COUNT += 1

except Exception:
    def play_beep():
        global BEEP_COUNT
        if BEEP_COUNT >= MAX_BEEPS:
            return
        print("\a")
        BEEP_COUNT += 1


class CheatingDetector:
    def __init__(self, evidence_dir):
        # Store last detected EXTRA boxes (xyxy + conf)
        self.last_extra_person_boxes = []  # list of dicts: {"xyxy": (x1,y1,x2,y2), "conf": float}

        # Heuristic thresholds (tune these!)
        self.visibility_thresh = 0.3
        self.edge_margin = 0.05

        # LEANING / HAND SIGNALS
        self.lean_side_threshold = 0.18  # distance from CENTER (0.5), not from edge
        self.head_low_threshold = 0.82  # more forgiving than 0.7
        self.shoulder_tilt_threshold = 0.12  # new: flags tilted torso
        self.hand_above_shoulder_margin = 0.03

        self.lean_confirm_seconds = 2.5  # must lean continuously this long to trigger
        self.lean_cooldown_seconds = 3.0  # after clearing, wait before re-arming

        self._lean_ema_x = None  # smoothed shoulder center
        self._lean_ema_alpha = 0.25  # EMA smoothing factor
        self._lean_first_seen = {}  # {reason_key: timestamp when it first appeared}
        self._lean_active = {}
        self._lean_cooldown_until = {}

        # Warning system
        self.warning_delay = 5.0
        self.max_warnings = 3

        # State (pose)
        self.prev_center_x = None

        self.current_violation_start = None
        self.current_violation_types = set()
        self.current_violation_messages = []
        self.warning_count = 0

        # Extra person state
        self.extra_person_current = False
        self.extra_person_ever_seen = False
        self.extra_person_first_time = None
        self.extra_person_duration = 0.0
        self.extra_person_confirm_seconds = 3.0
        self.extra_person_confirmed = False
        self.extra_person_initial_evidence_file = None

        # Statistics
        self.total_frames = 0
        self.violation_frames = 0
        self.violation_history = []

        # Warning events
        self.warning_events = []

        # Evidence folder
        self.evidence_dir = evidence_dir

        # # Hand-sign stability state
        # self._prev_sign_label = None
        # self._stable_sign_count = 0
        # -------------------------------
        # Event-based evidence (ONE shot per event)
        # -------------------------------
        self.event_states = {}  # key -> {active, start, evidence_taken, last_seen}
        self.event_log = []     # list of {time, key, duration, file, messages}

        # How long a violation must persist before we take ONE evidence
        # (tune as you like; 0.0 means "instant once")
        self.event_confirm_seconds = {
            "leaning": 0.0,
            "pose_not_detected": 2.0,
            "out_of_frame": 2.0,
            "extra_person": 3.0,          # aligns with your existing logic
            "explicit_hand_sign": 0.0     # take once immediately when recognized
        }

        # Optional: prevent re-triggering too quickly after it ends
        self.event_cooldown_seconds = 1.0


    def save_hand_sign_evidence(self, frame, sign_label, conf):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(
            self.evidence_dir,
            f"hand_sign_{sign_label}_{conf:.2f}_{timestamp}.jpg"
        )
        cv2.imwrite(filename, frame)
        print(f"[INFO] Saved hand-sign evidence: {filename}")
        return filename

    # ---------- Utility ----------
    @staticmethod
    def _dist_1d(a, b):
        return abs(a - b)

    @staticmethod
    def _dist_2d(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _is_landmark_visible(self, l):
        return (
            l.visibility > self.visibility_thresh and
            self.edge_margin <= l.x <= 1.0 - self.edge_margin and
            self.edge_margin <= l.y <= 1.0 - self.edge_margin
        )

    # ---------- Heuristics ----------
    def check_nose_visible(self, pose_landmarks):
        nose = pose_landmarks[0]

        if not self._is_landmark_visible(nose):
            return False, "Nose not visible (out of frame or low visibility)"

        return True, ""

    def check_leaning(self, pose_landmarks):
        now = time.time()

        left_sh = pose_landmarks[11]
        right_sh = pose_landmarks[12]
        nose = pose_landmarks[0]

        # Smooth the shoulder center with EMA to absorb single-frame jitter
        raw_cx = (left_sh.x + right_sh.x) / 2.0
        if self._lean_ema_x is None:
            self._lean_ema_x = raw_cx
        else:
            self._lean_ema_x = (self._lean_ema_alpha * raw_cx
                                + (1 - self._lean_ema_alpha) * self._lean_ema_x)
        center_x = self._lean_ema_x

        # Raw per-reason conditions
        raw_conditions = {
            "lean_left": center_x < (0.5 - self.lean_side_threshold),
            "lean_right": center_x > (0.5 + self.lean_side_threshold),
            "head_down": nose.y > self.head_low_threshold,
            "shoulder_tilt": abs(left_sh.y - right_sh.y) > self.shoulder_tilt_threshold,
        }

        reason_labels = {
            "lean_left": "Leaning to the left",
            "lean_right": "Leaning to the right",
            "head_down": "Leaning down (head too low)",
            "shoulder_tilt": "Significant shoulder tilt detected",
        }

        confirmed_reasons = []

        for key, is_active in raw_conditions.items():
            if not is_active:
                # Condition cleared — start cooldown, reset timer
                self._lean_active[key] = False
                if key in self._lean_first_seen:
                    if self._lean_cooldown_until.get(key, 0) < now:
                        self._lean_cooldown_until[key] = now + self.lean_cooldown_seconds
                    self._lean_first_seen.pop(key, None)
                continue

            # Skip if still in cooldown
            if now < self._lean_cooldown_until.get(key, 0):
                continue

            self._lean_active[key] = True
            if key not in self._lean_first_seen:
                self._lean_first_seen[key] = now

            elapsed = now - self._lean_first_seen[key]
            if elapsed >= self.lean_confirm_seconds:
                confirmed_reasons.append(reason_labels[key])

        self.prev_center_x = center_x

        if confirmed_reasons:
            return False, "; ".join(confirmed_reasons)
        return True, ""

    def check_hand_signals(self, pose_landmarks):
        """
        Pure geometric heuristic: is hand raised high relative to the shoulder?
        This is still used as a general suspicious pattern (e.g., waving).
        """
        left_sh = pose_landmarks[11]
        right_sh = pose_landmarks[12]
        left_wr = pose_landmarks[15]
        right_wr = pose_landmarks[16]

        reasons = []

        if left_wr.y < left_sh.y - self.hand_above_shoulder_margin:
            reasons.append("Left hand raised (possible signalling)")
        if right_wr.y < right_sh.y - self.hand_above_shoulder_margin:
            reasons.append("Right hand raised (possible signalling)")

        if reasons:
            return False, "; ".join(reasons)
        return True, ""

    def save_evidence_frame(self, frame, messages, prefix="evidence"):

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.evidence_dir, f"{prefix}_{self.warning_count}_{timestamp}.jpg")

        # Optional: write 1–2 messages on the frame for quick review
        try:
            y = 25
            for msg in messages[:3]:
                cv2.putText(frame, msg[:70], (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
                y += 22
        except:
            pass

        cv2.imwrite(filename, frame)
        print(f"[INFO] Saved evidence frame: {filename}")
        return filename

    # def is_any_hand_raised(self, pose_landmarks):
    #     """
    #     Helper for classifier gating.
    #     Returns True if at least one hand is clearly raised above its shoulder.
    #     This is used together with the classifier, so it's OK to be a bit strict.
    #     """
    #     left_sh = pose_landmarks[11]
    #     right_sh = pose_landmarks[12]
    #     left_wr = pose_landmarks[15]
    #     right_wr = pose_landmarks[16]
    #
    #     left_raised = left_wr.y < left_sh.y - self.hand_above_shoulder_margin
    #     right_raised = right_wr.y < right_sh.y - self.hand_above_shoulder_margin
    #
    #     return left_raised or right_raised
    def classify_hand_sign_rule_based(self, frame, hands_results):
        """
        Rule-based finger counting using MediaPipe Hands landmarks.
        Returns (label, confidence) for cheating gestures only, otherwise (None, None).
        """
        if frame is None or frame.size == 0:
            return None, None
        if not hands_results.multi_hand_landmarks or not hands_results.multi_handedness:
            return None, None

        h, w = frame.shape[:2]

        for hand_landmarks, hand_label in zip(hands_results.multi_hand_landmarks,
                                              hands_results.multi_handedness):
            label = hand_label.classification[0].label

            lm_list = []
            for lm in hand_landmarks.landmark:
                cx, cy = int(lm.x * w), int(lm.y * h)
                lm_list.append((cx, cy))

            fingers = []

            # Thumb
            if label == "Right":
                fingers.append(1 if lm_list[4][0] < lm_list[3][0] else 0)
            else:
                fingers.append(1 if lm_list[4][0] > lm_list[3][0] else 0)

            # Other 4 fingers
            for i in range(1, 5):
                tip_id = TIP_IDS[i]
                fingers.append(1 if lm_list[tip_id][1] < lm_list[tip_id - 2][1] else 0)

            current_gesture = None
            if fingers == [0, 0, 0, 0, 0]:
                current_gesture = "0"
            elif fingers == [0, 1, 0, 0, 0]:
                current_gesture = "1"
            elif fingers == [0, 1, 1, 0, 0]:
                current_gesture = "2"
            elif fingers == [0, 1, 1, 1, 0] or fingers == [0, 0, 1, 1, 1]:
                current_gesture = "3"
            elif fingers == [1, 1, 1, 1, 0] or fingers == [0, 1, 1, 1, 1]:
                current_gesture = "4"
            elif fingers == [1, 1, 1, 1, 1]:
                current_gesture = "5"

            if current_gesture in CHEATING_GESTURES:
                return current_gesture, 1.0
            if current_gesture in NON_CHEATING_GESTURES:
                return None, None

        return None, None

    def check_extra_person(self, frame):
        """
        Use YOLO to detect extra persons in the frame.
        Filters out:
        - low-confidence boxes
        - very small boxes (tiny blobs, noise)
        """
        if yolo_model is None:
            self.extra_person_current = False
            self.extra_person_duration = 0.0
            self.extra_person_first_time = None
            return False, ""

        results = yolo_model(frame, verbose=False)
        if not results:
            self.extra_person_current = False
            self.extra_person_duration = 0.0
            self.extra_person_first_time = None
            return False, ""

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            self.extra_person_current = False
            self.extra_person_duration = 0.0
            self.extra_person_first_time = None
            return False, ""

        h, w, _ = frame.shape
        frame_area = float(w * h)

        num_persons = 0
        for b in boxes:
            cls_id = int(b.cls[0])
            conf = float(b.conf[0])

            # keep only "person" class
            if cls_id != 0:
                continue

            # filter on confidence
            if conf < EXTRA_PERSON_CONF_THRESH:
                continue

            x1, y1, x2, y2 = b.xyxy[0]
            box_w = float(x2 - x1)
            box_h = float(y2 - y1)
            box_area = box_w * box_h
            area_frac = box_area / frame_area if frame_area > 0 else 0.0

            # ignore very small boxes (likely artifacts)
            if area_frac < EXTRA_PERSON_MIN_AREA_FRAC:
                continue

            num_persons += 1

        now = time.time()

        if num_persons > 1:
            # At least 2 real, big, confident person boxes
            if not self.extra_person_current:
                self.extra_person_current = True
                self.extra_person_first_time = now
                # if not self.extra_person_ever_seen:
                #     self.extra_person_ever_seen = True
                #     self.extra_person_initial_evidence_file = self.save_evidence_frame(
                #         frame, ["Initial extra person detection"], prefix="extra_person_initial"
                #     )
                #
                #     print("[INFO] Extra person first seen, initial evidence saved.")

            if self.extra_person_first_time is None:
                self.extra_person_first_time = now
            self.extra_person_duration = now - self.extra_person_first_time

            if (self.extra_person_duration >= self.extra_person_confirm_seconds
                    and not self.extra_person_confirmed):
                self.extra_person_confirmed = True
                print(f"[INFO] Extra person confirmed (duration >= {self.extra_person_confirm_seconds}s).")

            msg = (
                f"Extra person detected in frame (count={num_persons}, "
                f"current duration≈{self.extra_person_duration:.1f}s)"
            )
            return True, msg
        else:
            self.extra_person_current = False
            self.extra_person_duration = 0.0
            self.extra_person_first_time = None
            return False, ""

    def evaluate_frame(self, frame, pose_results):
        self.total_frames += 1
        violation_types = set()
        violation_messages = []

        # Extra person
        extra_flag, extra_msg = self.check_extra_person(frame)
        if extra_flag:
            violation_types.add("extra_person")
            violation_messages.append(extra_msg)

        # Pose-related checks
        if not pose_results.pose_landmarks:
            violation_types.add("pose_not_detected")#can't see the body due to lighting or unclear pose or person left camera
            violation_messages.append("Student not visible (pose not detected)")

        else:
            pose_landmarks= pose_results.pose_landmarks.landmark

            ok_vis, msg_vis = self.check_nose_visible(pose_landmarks)
            if not ok_vis:
                violation_types.add("out_of_frame")
                violation_messages.append(msg_vis)


            ok_lean, msg_lean = self.check_leaning(pose_landmarks)
            if not ok_lean:
                violation_types.add("leaning")
                violation_messages.append(msg_lean)



        if violation_types:
            self.violation_frames += 1
            self.violation_history.append((time.time(), list(violation_types)))

        return violation_types, violation_messages
    def update_events(self, violation_types, violation_messages, frame, explicit_sign=None):
        """
        Event-based evidence:
        - Each violation type is tracked independently.
        - ONE evidence screenshot per event (when it lasts >= confirm seconds).
        - New evidence only after the event ends (and cooldown passes).
        explicit_sign: (label, conf) or None
        """
        now = time.time()

        # Expand hand sign into its own event key (per label)
        # so "1 held for 5 minutes" => only 1 screenshot.
        extra_keys = set()
        if explicit_sign is not None:
            sign_label, conf = explicit_sign
            # Use per-label key so a different sign becomes a new event
            extra_keys.add(f"explicit_hand_sign:{sign_label}")

        # Build the set of "active keys" this frame
        active_keys = set(violation_types) | extra_keys

        # 1) Mark/advance active events
        for key in active_keys:
            st = self.event_states.get(key)

            # Determine base type for thresholds
            base_type = key.split(":")[0]

            confirm_s = self.event_confirm_seconds.get(base_type, 2.0)

            # Per-sign confirm time for explicit hand signs
            if base_type == "explicit_hand_sign":
                sign_label = key.split(":", 1)[1]
                if sign_label in {"1", "2", "3", "4"}:
                    confirm_s = 0.0  # instant
                else:
                    confirm_s = 1.0  # example delay for other signs (tune)

            if st is None:
                # start new event
                self.event_states[key] = {
                    "active": True,
                    "start": now,
                    "evidence_taken": False,
                    "last_seen": now,
                }
                st = self.event_states[key]
                # beep once at event start (optional)
                play_beep()
            else:
                # continue existing event
                st["active"] = True
                st["last_seen"] = now

            # Take evidence ONCE when it passes confirm time
            elapsed = now - st["start"]
            if (not st["evidence_taken"]) and (elapsed >= confirm_s):
                self.warning_count += 1

                # Make prefix readable & unique
                safe_key = key.replace(":", "_")
                msgs = violation_messages.copy()

                # If it's a hand sign key, attach a clear message
                if base_type == "explicit_hand_sign":
                    sign_label = key.split(":", 1)[1]
                    msgs = [f"Recognized hand sign '{sign_label}'"] + msgs

                evidence_file = self.save_evidence_frame(
                    frame, msgs, prefix=safe_key
                )
                st["evidence_taken"] = True

                self.event_log.append({
                    "time": now,
                    "key": key,
                    "duration": round(elapsed, 2),
                    "file": evidence_file,
                    "messages": msgs
                })

        # 2) Close events that disappeared (end of event)
        for key, st in list(self.event_states.items()):
            if not st.get("active"):
                continue
            if key not in active_keys:
                # event ended this frame
                st["active"] = False
                st["end"] = now
                st["cooldown_until"] = now + self.event_cooldown_seconds

        # 3) Cleanup (optional): drop old inactive events after cooldown
        for key, st in list(self.event_states.items()):
            if st.get("active"):
                continue
            if st.get("cooldown_until", 0) <= now:
                # allow future fresh events; remove state
                self.event_states.pop(key, None)

    # def update_warnings(self, violation_types, violation_messages, frame):
    #     now = time.time()
    #
    #     if violation_types:
    #         if not self.current_violation_types:
    #             self.current_violation_start = now
    #             self.current_violation_types = violation_types.copy()
    #             self.current_violation_messages = violation_messages.copy()
    #             play_beep()
    #         else:
    #             self.current_violation_types |= violation_types
    #             for m in violation_messages:
    #                 if m not in self.current_violation_messages:
    #                     self.current_violation_messages.append(m)
    #
    #             elapsed = now - self.current_violation_start
    #             if elapsed >= self.warning_delay:
    #                 self.warning_count += 1
    #                 # build a readable prefix from the violation types
    #                 prefix = "_".join(
    #                     sorted(self.current_violation_types)) if self.current_violation_types else "evidence"
    #                 evidence_file = self.save_evidence_frame(frame, self.current_violation_messages, prefix=prefix)
    #
    #                 self.warning_events.append({
    #                     "time": now,
    #                     "types": self.current_violation_types.copy(),
    #                     "messages": self.current_violation_messages.copy(),
    #                     "file": evidence_file
    #                 })
    #                 print(f"[WARN] Warning #{self.warning_count} registered.")
    #                 play_beep()
    #                 self.current_violation_start = now
    #     else:
    #         self.current_violation_types = set()
    #         self.current_violation_messages = []
    #         self.current_violation_start = None

    def compute_final_probability(self):
        if self.extra_person_confirmed:
            expl = f"Extra person stayed in frame for at least {self.extra_person_confirm_seconds} seconds."
            return 1.0, expl

        if self.total_frames == 0:
            return 0.0, "No frames processed."

        violation_ratio = self.violation_frames / self.total_frames
        warning_ratio = self.warning_count / max(1, self.max_warnings)

        prob = 0.7 * warning_ratio + 0.3 * violation_ratio
        prob = min(prob, 0.85)
        prob = max(0.0, min(1.0, prob))

        explanation = (
            f"Warnings: {self.warning_count}/{self.max_warnings}, "
            f"Violation frames: {self.violation_frames}/{self.total_frames} "
            f"({violation_ratio:.2f})."
        )

        if self.extra_person_ever_seen and not self.extra_person_confirmed:
            explanation += (
                f" Extra person was briefly seen in the frame (duration < {self.extra_person_confirm_seconds}s); "
                "please review evidence."
            )

        return prob, explanation

    def describe_warning_events(self):
        if not self.warning_events:
            return ["No warnings were issued during this session."]

        descriptions = []
        for i, ev in enumerate(self.warning_events, start=1):
            msgs = ev.get("messages", [])
            file = ev.get("file", "N/A")
            joined = "; ".join(msgs) if msgs else "Unspecified violations"
            descriptions.append(f"Warning #{i}: {joined} | Evidence: {file}")
        return descriptions


def main():
    cap = cv2.VideoCapture(0)
    evidence_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence")
    os.makedirs(evidence_dir, exist_ok=True)

    detector = CheatingDetector(evidence_dir)

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose, mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as hands:

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            results_pose = pose.process(rgb)
            results_hands = hands.process(rgb)

            # -------- Rule-based hand sign classification --------
            recognized_sign, recognized_conf = detector.classify_hand_sign_rule_based(
                frame, results_hands
            )

            # -------- Pose + YOLO heuristics --------
            violation_types, violation_messages = detector.evaluate_frame(
                frame, results_pose
            )

            # Only count explicit cheating hand signs
            explicit_sign = None
            if recognized_sign is not None:
                violation_types.add("explicit_hand_sign")
                violation_messages.append(
                    f"Recognized hand sign '{recognized_sign}'"
                )
                explicit_sign = (recognized_sign, recognized_conf)

            #detector.update_warnings(violation_types, violation_messages, frame)
            detector.update_events(violation_types, violation_messages, frame, explicit_sign=explicit_sign)

            # -------- Overlay UI --------
            y0 = 30
            dy = 25

            status_text = f"Warnings: {detector.warning_count}/{detector.max_warnings}"
            if detector.extra_person_confirmed:
                status_text += " | EXTRA PERSON CONFIRMED"
            elif detector.extra_person_current:
                status_text += " | EXTRA PERSON PRESENT"
            cv2.putText(frame, status_text, (10, y0),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255 if detector.warning_count > 0 else 255), 2)

            if 'extra_person' in violation_types:
                cv2.putText(frame, "🚨 EXTRA PERSON DETECTED 🚨",
                            (10, y0 + dy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 0, 255), 2)
                cv2.putText(frame, "Another person is visible. They must leave the frame.",
                            (10, y0 + 2*dy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 0, 255), 2)

            # Show sign only if it's considered a cheating signal
            if recognized_sign is not None:
                cv2.putText(frame, f"Sign: {recognized_sign}",
                            (10, y0 + 3*dy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (255, 0, 0), 2)

            if violation_types:
                y = y0 + 4*dy if 'extra_person' in violation_types else y0 + 2*dy
                cv2.putText(frame, "⚠ Suspicious behavior detected!",
                            (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                y += dy
                cv2.putText(frame, "Please adjust your position:",
                            (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                y += dy

                for msg in violation_messages:
                    short_msg = msg[:60]
                    cv2.putText(frame, f"- {short_msg}", (10, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    y += dy

                if detector.current_violation_start is not None:
                    remaining = detector.warning_delay - (time.time() - detector.current_violation_start)
                    if remaining < 0:
                        remaining = 0
                    y += dy
                    cv2.putText(frame, f"Warning in: {remaining:.1f} s",
                                (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

            cv2.imshow("Pose-based Cheating Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()

    print("\n========== SESSION SUMMARY ==========")
    warning_descriptions = detector.describe_warning_events()
    print("Warnings detail:")
    for line in warning_descriptions:
        print("  -", line)

    prob, explanation = detector.compute_final_probability()

    if prob < 0.3:
        status = "Clean"
    elif prob < 0.6:
        status = "Suspicious"
    else:
        status = "Highly suspicious"

    print(f"\nCheating probability: {prob * 100:.1f}% ({status})")
    print(f"Explanation: {explanation}")
    if detector.extra_person_confirmed:
        print("Reason: Extra person remained in frame beyond "
              f"{detector.extra_person_confirm_seconds} seconds.")


if __name__ == "__main__":
    main()