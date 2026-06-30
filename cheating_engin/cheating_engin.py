import csv
import os
import shutil
from collections import defaultdict


EVENT_WEIGHT = 1 / 21
WEBCAM_WEIGHT = EVENT_WEIGHT / 9
SYSTEM_WEIGHT = EVENT_WEIGHT / 3

# -------------------------
# Audio Weights
# -------------------------
AUDIO_WEIGHTS = {
    "DIFFERENT_SPEAKER": EVENT_WEIGHT,
    "OVERLAP": EVENT_WEIGHT,
    "SAME_PERSON_TOO_MUCH": EVENT_WEIGHT
}

# -------------------------
# Forbidden Objects
# -------------------------
FORBIDDEN_OBJECTS = ["mobile", "book", "watch",
                     "headphones", "sunglass", "earbuds",
                     "laptop", "face_mask", "calculator"]

# -------------------------
# Webcam Violation Weights
# -------------------------
OBJECT_WEIGHTS = {
    "mobile": WEBCAM_WEIGHT,
    "calculator": WEBCAM_WEIGHT,
    "laptop": WEBCAM_WEIGHT,
    "book": WEBCAM_WEIGHT,
    "headphones": WEBCAM_WEIGHT,
    "earbuds": WEBCAM_WEIGHT,
    "watch": WEBCAM_WEIGHT,
    "sunglass": WEBCAM_WEIGHT,
    "face_mask": WEBCAM_WEIGHT
}

WEBCAM_WEIGHTS = {
    "extra_person": EVENT_WEIGHT,
    "out_of_frame": EVENT_WEIGHT,
    "hand_sign": EVENT_WEIGHT,
    "leaning": EVENT_WEIGHT
}

SYSTEM_WEIGHTS = {
    "Tab Switched": SYSTEM_WEIGHT,
    "Shortcut": SYSTEM_WEIGHT,
    "Window Lost Focus": SYSTEM_WEIGHT
}


# -------------------------
# Helpers
# -------------------------
def count_events(csv_file):
    event_counts = defaultdict(int)
    try:
        with open(csv_file, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                event = row["Event"]
                event_counts[event] += 1
    except FileNotFoundError:
        print(f"Warning: System file '{csv_file}' not found. System risk set to 0.")
    return dict(event_counts)
#
#
# def get_student_paths(student_id):
#     """Build all CSV paths for a given student."""
#     return {
#         "audio":  os.path.join("static", "suspicious_events", f"suspicious_events_{student_id}.csv"),
#         "system": os.path.join("static", "system_events",     f"system_events_{student_id}.csv"),
#     }


# -------------------------
# Audio Risk
# -------------------------
def calculate_audio_risk(student_id, exam_id, exam_duration_sec):
    csv_file = os.path.join(
        "static",
        "suspicious_events",
        f"suspicious_events_{student_id}_{exam_id}.csv"
    )

    event_durations = defaultdict(float)
    event_counts    = defaultdict(int)

    try:
        with open(csv_file, mode="r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                event    = row["event_label"]
                duration = float(row["duration_sec"])
                event_durations[event] += duration
                event_counts[event]    += 1
    except FileNotFoundError:
        print(f"Warning: Audio file '{csv_file}' not found. Audio risk set to 0.")
        return 0.0

    audio_risk = 0.0
    for event, weight in AUDIO_WEIGHTS.items():
        total_duration = event_durations.get(event, 0.0)
        num_repeats    = event_counts.get(event, 0)
        audio_risk    += weight * num_repeats

    return min(audio_risk, 1.0)


# -------------------------
# Webcam Risk
# -------------------------
def calculate_webcam_risk(student_id, exam_id, exam_duration_sec):
    webcam_csv = os.path.join(
        f"evidence_{student_id}_{exam_id}",
        "report.csv"
    )
    object_counts   = defaultdict(int)
    behavior_counts = defaultdict(int)

    object_rows  = 0
    hand_rows    = 0
    extra_rows   = 0
    outframe_rows= 0
    leaning_rows = 0
    gaze_duration= 0.0

    try:
        with open(webcam_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:

                # Objects
                violation = row.get("Violation", "").strip().lower()
                if violation:
                    object_rows += 1
                    for obj in FORBIDDEN_OBJECTS:
                        if obj in violation:
                            object_counts[obj] += 1
                            break

                # Gaze
                gaze = row.get("Gaze_Direction", "").strip().lower()
                try:
                    duration = float(row.get("duration_seconds", 0))
                except:
                    duration = 0.0
                if gaze and gaze != "center":
                    gaze_duration += duration

                # Hand Sign
                hand = row.get("Hand_Sign", "").strip()
                if hand:
                    hand_rows += 1
                if hand == "Yes":
                    behavior_counts["hand_sign"] += 1

                # Extra Person
                extra = row.get("Extra_Person", "").strip()
                if extra:
                    extra_rows += 1
                if extra == "Yes":
                    behavior_counts["extra_person"] += 1

                # Out of Frame
                outframe = row.get("Out_Frame", "").strip()
                if outframe:
                    outframe_rows += 1
                if outframe == "Yes":
                    behavior_counts["out_of_frame"] += 1

                # Leaning
                leaning = row.get("leaning", "").strip()
                if leaning:
                    leaning_rows += 1
                if leaning == "Yes":
                    behavior_counts["leaning"] += 1

    except FileNotFoundError:
        print(f"Warning: Webcam file '{webcam_csv}' not found.")
        return 0.0

    webcam_risk = 0.0

    # Object risk
    if object_rows > 0:
        for obj, count in object_counts.items():
            weight           = OBJECT_WEIGHTS.get(obj, 0.5)
            normalized_count = count / object_rows
            webcam_risk     += weight * normalized_count

    # Behavioral risk
    behavior_rows = {
        "hand_sign":    hand_rows,
        "extra_person": extra_rows,
        "out_of_frame": outframe_rows,
        "leaning":      leaning_rows
    }
    for behavior, count in behavior_counts.items():
        rows = behavior_rows.get(behavior, 0)
        if rows > 0:
            weight           = WEBCAM_WEIGHTS.get(behavior, 0.5)
            normalized_count = count / rows
            webcam_risk     += weight * normalized_count

    # Gaze risk
    if exam_duration_sec > 0:
        gaze_ratio   = gaze_duration / exam_duration_sec
        webcam_risk += EVENT_WEIGHT * gaze_ratio

    return min(webcam_risk, 1.0)


# -------------------------
# System Risk
# -------------------------
def calculate_system_risk(student_id, exam_id):
    system_csv = os.path.join(
        "static",
        "system_events",
        f"system_events_{student_id}_{exam_id}.csv"
    )
    event_counts = count_events(system_csv)

    if not event_counts:
        return 0.0

    system_risk  = 0.0
    total_events = sum(event_counts.values())

    for event, count in event_counts.items():
        weight      = SYSTEM_WEIGHTS.get(event, EVENT_WEIGHT)
        normalized  = count / total_events
        system_risk += weight * normalized

    return min(system_risk, 1.0)


# -------------------------
# Combined Risk
# -------------------------
def calculate_combined_cheating_risk(student_id, exam_id, exam_duration_sec):

    audio_risk  = calculate_audio_risk(student_id, exam_id, exam_duration_sec)
    system_risk = calculate_system_risk(student_id, exam_id)
    webcam_risk = calculate_webcam_risk(student_id, exam_id, exam_duration_sec)

    combined_risk = audio_risk + webcam_risk + system_risk

    return {
        "audio_risk":           round(audio_risk,  4),
        "webcam_risk":          round(webcam_risk, 4),
        "system_risk":          round(system_risk, 4),
        "combined_risk":        round(min(combined_risk, 1.0), 4),

        "audio_percentage":     round(audio_risk  * 100, 2),
        "webcam_percentage":    round(webcam_risk * 100, 2),
        "system_percentage":    round(system_risk * 100, 2),
        "combined_percentage":  round(min(combined_risk, 1.0) * 100, 2),

        "risk_level": get_risk_level(combined_risk)
    }

# -------------------------
# Risk Level
# -------------------------
def get_risk_level(risk_score):
    if risk_score < 0.2:
        return "LOW"
    elif risk_score < 0.4:
        return "MODERATE"
    elif risk_score < 0.6:
        return "MEDIUM-HIGH"
    elif risk_score < 0.8:
        return "HIGH"
    else:
        return "CRITICAL"


# -------------------------
# Report
# -------------------------
def generate_cheating_report(student_id, exam_id, exam_duration_sec):

    results = calculate_combined_cheating_risk(
        student_id,
        exam_id,
        exam_duration_sec
    )

    report_folder = os.path.join("static", "reports", f"report_{student_id}_{exam_id}")
    os.makedirs(report_folder, exist_ok=True)

    # ── DEBUG — print all paths before doing anything ────────────
    base_dir     = os.path.dirname(os.path.abspath(__file__))
    evidence_dir = os.path.join(base_dir, f"evidence_{student_id}_{exam_id}")
    audio_src    = os.path.join("static", "suspicious_events", f"suspicious_events_{student_id}.csv")
    system_src   = os.path.join("static", "system_events",     f"system_events_{student_id}.csv")

    print(f"\n[RISK DEBUG] ── Path Check ──────────────────────────")
    print(f"[RISK DEBUG] base_dir      : {base_dir}")
    print(f"[RISK DEBUG] evidence_dir  : {evidence_dir} → exists={os.path.exists(evidence_dir)}")
    print(f"[RISK DEBUG] audio_src     : {audio_src}    → exists={os.path.exists(audio_src)}")
    print(f"[RISK DEBUG] system_src    : {system_src}   → exists={os.path.exists(system_src)}")
    print(f"[RISK DEBUG] report_folder : {report_folder}")
    print(f"[RISK DEBUG] ─────────────────────────────────────────\n")
    # ─────────────────────────────────────────────────────────────

    # ── 1. Save risk summary CSV ──────────────────────────────────
    summary_file = os.path.join(report_folder, "risk_summary.csv")
    with open(summary_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["student_id",         student_id])
        writer.writerow(["exam_id",             exam_id])
        writer.writerow(["audio_risk",          results["audio_risk"]])
        writer.writerow(["webcam_risk",         results["webcam_risk"]])
        writer.writerow(["system_risk",         results["system_risk"]])
        writer.writerow(["combined_risk",       results["combined_risk"]])
        writer.writerow(["audio_percentage",    results["audio_percentage"]])
        writer.writerow(["webcam_percentage",   results["webcam_percentage"]])
        writer.writerow(["system_percentage",   results["system_percentage"]])
        writer.writerow(["combined_percentage", results["combined_percentage"]])
        writer.writerow(["risk_level",          results["risk_level"]])

    # ── 2. Copy webcam evidence ───────────────────────────────────
    webcam_dest = os.path.join(report_folder, "webcam_evidence")
    if os.path.exists(evidence_dir):
        if os.path.exists(webcam_dest):
            shutil.rmtree(webcam_dest)
        shutil.copytree(evidence_dir, webcam_dest)
        print(f"[RISK] ✅ Webcam evidence copied → {webcam_dest}")
    else:
        print(f"[RISK] ❌ Evidence dir NOT found: {evidence_dir}")

    # ── 3. Copy audio CSV ─────────────────────────────────────────
    audio_dest = os.path.join(report_folder, f"audio_events_{student_id}.csv")
    if os.path.exists(audio_src):
        shutil.copy2(audio_src, audio_dest)
        print(f"[RISK] ✅ Audio events copied → {audio_dest}")
    else:
        print(f"[RISK] ❌ Audio src NOT found: {audio_src}")

    # ── 4. Copy system CSV ────────────────────────────────────────
    system_dest = os.path.join(report_folder, f"system_events_{student_id}.csv")
    if os.path.exists(system_src):
        shutil.copy2(system_src, system_dest)
        print(f"[RISK] ✅ System events copied → {system_dest}")
    else:
        print(f"[RISK] ❌ System src NOT found: {system_src}")

    print(f"\n[RISK] Final folder contents: {os.listdir(report_folder)}\n")

    print("\n" + "="*70)
    print("CHEATING DETECTION REPORT")
    print("="*70)
    print(f"Audio Risk:        {results['audio_percentage']:6.2f}%")
    print(f"Webcam Risk:       {results['webcam_percentage']:6.2f}%")
    print(f"System Risk:       {results['system_percentage']:6.2f}%")
    print("-"*70)
    print(f"COMBINED RISK:     {results['combined_percentage']:6.2f}%")
    print(f"RISK LEVEL:        {results['risk_level']}")
    print("="*70)

    return results

#Analyze Detected Objects
# -------------------------
def analyze_detected_objects(csv_file):
    detected_objects = defaultdict(int)
    try:
        with open(csv_file, mode="r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                detected = row.get("Detected_Objects", "")
                if detected:
                    for obj in FORBIDDEN_OBJECTS:
                        if obj.lower() in detected.lower():
                            detected_objects[obj] += 1
    except FileNotFoundError:
        pass
    return dict(detected_objects)


# -------------------------
# Example Usage
# -------------------------
# if __name__ == "__main__":
#     results = generate_cheating_report(
#         student_id=101,
#         webcam_csv="static/webcam_violations/webcam_101.csv",
#         exam_duration_sec=300
#     )