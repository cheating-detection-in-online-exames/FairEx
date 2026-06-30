import os
import pathlib

# Fix: Windows symlink requires admin — use copy instead
_original_symlink_to = pathlib.Path.symlink_to


def _safe_symlink_to(self, target, target_is_directory=False):
    try:
        _original_symlink_to(self, target, target_is_directory)
    except OSError:
        import shutil
        shutil.copy2(str(target), str(self))


pathlib.Path.symlink_to = _safe_symlink_to
import random
import uuid
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from core import db
import os
from core import utils
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from core import validators
from werkzeug.utils import secure_filename
from datetime import datetime
import numpy as np
import json
import cv2
import mediapipe as mp
import tensorflow as tf
import torch
from core.audio_utils import get_speaker_embedding, analyze_audio_chunk
from core.image_utils import verify_arcface, verify_arcface_live
from core.train_yolo_for_ID import detect_id_objects, is_egyptian_id, crop_face
from cheating_engin.cheating_engin import generate_cheating_report

SIMILARITY_THRESHOLD = 0.4
# ------------------------------------------------------->
# HHH = r"H:\Graduation Preject\electronics-website\electronics-website\static"

HHH = r"static"

save_path = r"static\faces\saved"
os.makedirs(save_path, exist_ok=True)  # this will create folders if missing

save_path = r"static\voices\saved"
os.makedirs(save_path, exist_ok=True)  #

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = "SUPER-SECRET"
SERVER_BOOT_ID = str(uuid.uuid4())  # changes every server restart
limiter = Limiter(app=app, key_func=get_remote_address,
                  default_limits=["50 per minute"], storage_uri="memory://")

UPLOAD_FOLDER = 'static/uploads'

connection = db.connect_to_database()

from core.db import load_exam_questions as _load_exam_questions

# db.init_db(connection)
from functools import wraps
from flask import redirect, session, url_for, flash


def enforce_single_device(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))

        if session.get('boot_id') != SERVER_BOOT_ID:
            session.clear()
            return redirect(url_for('login'))

        # Get the role from the session (default to student)
        role = session.get('role', 'student')

        # Pass the role to the database function!
        db_token = db.get_active_session(connection, session['username'], role)
        current_token = session.get('device_token')

        if db_token != current_token:
            session.clear()
            flash("You were logged out because your account is active on another device.", "danger")
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return wrapper

# def enforce_single_device(f):
#     @wraps(f)
#     def wrapper(*args, **kwargs):
#         if 'username' not in session:
#             return redirect(url_for('login'))
#
#         db_token = db.get_active_session(connection, session['username'])
#         current_token = session.get('device_token')
#
#         if db_token != current_token:
#             session.clear()
#             flash("You were logged out because your account is active on another device.", "danger")
#             return redirect(url_for('login'))
#
#         return f(*args, **kwargs)
#
#     return wrapper
#

@app.route('/', methods=['POST', 'GET'])
@enforce_single_device
def index():
    if 'username' in session:
        username = session.get('username')
        if username == 'admin' or session.get('role') == 'doctor':
            return redirect(url_for('admin_dashboard'))
        else:
            # Get real student info first so we can filter exams by level/department
            _user = db.get_user(connection, username)
            _name = _user['username'] if _user else username
            _level_raw = str(_user['level']) if _user else "1"
            _dept = _user['department'] if _user else ""
            # Normalize "Level 1" → "1" to match the integer stored in exams.level
            import re as _re
            _level_match = _re.search(r'\d+', _level_raw)
            _level_num = _level_match.group() if _level_match else _level_raw
            _level = _level_raw  # keep original for display

            # Pull published exams that match the student's department AND level (both must match)
            try:
                _exams = connection.execute(
                    """SELECT * FROM exams
                       WHERE status='published'
                         AND department=?
                         AND CAST(level AS TEXT)=?
                       ORDER BY start_datetime""",
                    (_dept, _level_num)
                ).fetchall()
                upcoming_exams = [
                    {
                        "id": e["id"],
                        "course_name": e["title"],
                        "date": e["start_datetime"][:10] if e["start_datetime"] else "",
                        "time": e["start_datetime"][11:16] if e["start_datetime"] and len(
                            e["start_datetime"]) > 10 else "",
                        "duration": e["duration_mins"],
                    }
                    for e in _exams
                ]
            except Exception:
                upcoming_exams = []

            courses = []
            announcements = [
                {"date": "2026-02-10", "message": "Exam schedule released."},
                {"date": "2026-02-11", "message": "Library will be closed on Friday."},
            ]

            return render_template(
                'index.html',
                student_name=_name,
                student_level=_level,
                student_department=_dept,
                upcoming_exams=upcoming_exams,
                courses=courses,
                announcements=announcements
            )
    # If no user in session, redirect to login
    return redirect(url_for('login'))


@app.route('/start_exam/<int:exam_id>')
def start_exam(exam_id):
    # For testing, we just show exam info
    exam_data = {
        1: {"course_name": "Math", "duration": 90},
        2: {"course_name": "Physics", "duration": 120},
    }

    exam = exam_data.get(exam_id, {"course_name": "Unknown", "duration": 0})

    return f"<h1>Exam Page</h1><p>Exam: {exam['course_name']}</p><p>Duration: {exam['duration']} mins</p>"


@app.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'temp_user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_code = request.form.get('code')
        real_code = session.get('2fa_code')

        if user_code == real_code:
            # 2FA success → user fully logged in
            username = session['temp_user']
            session['username'] = username

            # 1. Get the role we saved during the login step (default to student)
            role = session.get('role', 'student')

            # ------ Generate new unique device session ------
            device_token = str(uuid.uuid4())
            session['device_token'] = device_token
            session['boot_id'] = SERVER_BOOT_ID

            # 2. Save it in DB (Pass the role here so it updates the correct table!)
            db.set_active_session(connection, username, device_token, role)

            # remove temp values
            session.pop('temp_user', None)
            session.pop('2fa_code', None)

            # 3. Redirect based on the user's role
            if role == 'doctor':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))

        else:
            flash("Invalid code. Try again.", "danger")

    return render_template('verify_2fa.html')


# @app.route('/verify_2fa', methods=['GET', 'POST'])
# def verify_2fa():
#     if 'temp_user' not in session:
#         return redirect(url_for('login'))
#
#     if request.method == 'POST':
#         user_code = request.form.get('code')
#         real_code = session.get('2fa_code')
#
#         if user_code == real_code:
#             # 2FA success → user fully logged in
#             session['username'] = session['temp_user']
#
#             username = session['temp_user']
#             # ------ Generate new unique device session ------
#             device_token = str(uuid.uuid4())
#             session['device_token'] = device_token
#
#             # Save it in DB
#             db.set_active_session(connection, username, device_token)
#
#             # remove temp values
#             session.pop('temp_user', None)
#             session.pop('2fa_code', None)
#
#             # redirect based on user type
#             if session['username'] == 'admin':
#                 return redirect(url_for('admin_dashboard'))
#             return redirect(url_for('index'))
#         else:
#             flash("Invalid code. Try again.", "danger")
#
#     return render_template('verify_2fa.html')

@app.route('/login', methods=['POST', 'GET'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role     = request.form.get('role', 'student')  # "student" or "doctor"

        # Search the correct table based on role
        if role == 'doctor':
            user = db.get_doctor(connection, username)
        else:
            user = db.get_user(connection, username)

        if user:
            if utils.is_password_match(password, user[2]):
                session['temp_user'] = username
                session['id']        = user[3] if role == 'student' else user[0]  # doctors may not have stu_id
                session['role']      = role     # ← store role in session for later use

                # Generate & send 2FA code
                code = "999999"
               # code=random.randint(100000, 999999)
                session['2fa_code'] = str(code)
                utils.send_2fa_code(user[4], code)

                return redirect(url_for('verify_2fa'))
            else:
                flash("Wrong password", "danger")
                return render_template('login.html')
        else:
            flash(f"No {role} account found with that username", "danger")
            return render_template('login.html')

    return render_template('login.html')



@app.route('/logout')
def logout():
    if 'username' in session:
        role = session.get('role', 'student')
        db.clear_active_session(connection, session['username'], role)
    session.clear()
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def signUp():
    if request.method == 'POST':
        # -----------------------
        # Get role first
        # -----------------------
        role = request.form.get('role', 'student')  # "student" or "doctor"

        # -----------------------
        # Personal Information (both roles)
        # -----------------------
        username   = request.form.get('username')
        password   = request.form.get('password')
        email      = request.form.get('email')
        phone      = request.form.get('phone')

        # Basic validation (shared)
        if not all([username, password, email, phone]):
            flash("Missing Data", "danger")
            return render_template('signUp.html')

        if not utils.valid_username(username):
            flash("Invalid username", "danger")
            return render_template('signUp.html')

        if not utils.is_strong_password(password):
            flash("Weak Password. Please choose a stronger one.", "danger")
            return render_template('signUp.html')

        if not utils.valid_email(email):
            flash("Invalid email", "danger")
            return render_template('signUp.html')

        if not utils.valid_phone(phone):
            flash("Invalid phone number", "danger")
            return render_template('signUp.html')

        # Check if username already exists
        if db.get_user(connection, username):
            flash("Username already exists.", "danger")
            return render_template('signUp.html')

        # ======================================================
        # DOCTOR — save only personal info, no biometrics
        # ======================================================
        if role == 'doctor':
            db.add_doctor(
                connection=connection,
                username=username,
                password=password,

                phone=phone,
                email=email
            )
            flash("Doctor registration successful!", "success")
            return redirect(url_for('login'))

        # ======================================================
        # STUDENT — full registration with biometrics
        # ======================================================
        stu_id     = request.form.get('stu_id')
        level      = request.form.get('level')
        department = request.form.get('department')

        if not all([stu_id, level, department]):
            flash("Missing student academic information", "danger")
            return render_template('signUp.html')

        # -----------------------
        # Profile image (ID card)
        # -----------------------
        import os
        face_file      = request.files.get('profile_image')
        face_path      = None
        face_crop_path = None
        face_encoding  = None

        if face_file and face_file.filename != "":
            filename  = f"{stu_id}.jpg"
            face_path = os.path.join(HHH, "faces", "saved", filename)
            face_file.save(face_path)

            # Detect ID objects
            boxes, classes, scores = detect_id_objects(face_path)

            if boxes.size == 0 or not is_egyptian_id(classes):
                flash("Uploaded image is not a valid Egyptian ID!", "danger")
                return render_template('signUp.html')

            # Crop face from ID
            face_crop_path = crop_face(
                face_path, boxes, classes,
                save_dir=os.path.join(HHH, "faces", "cropped")
            )

            if not face_crop_path:
                flash("No face detected on ID!", "danger")
                return render_template('signUp.html')

            face_encoding = face_crop_path

        # -----------------------
        # Voice intro
        # -----------------------
        voice_data      = request.form.get("voice_intro")
        voice_embedding = None
        voice_path      = None

        if voice_data:
            import base64, os, torch
            import numpy as np
            import soundfile as sf
            from pydub import AudioSegment

            try:
                header, encoded = voice_data.split(",", 1)
                audio_bytes     = base64.b64decode(encoded)

                temp_raw = os.path.join(HHH, "voices", "saved", f"temp_{stu_id}.webm")
                wav_path = os.path.join(HHH, "voices", "saved", f"{stu_id}_voice.wav")

                with open(temp_raw, "wb") as f:
                    f.write(audio_bytes)

                # Convert webm → wav
                audio = AudioSegment.from_file(temp_raw)
                audio = audio.set_frame_rate(16000).set_channels(1)
                audio.export(wav_path, format="wav")
                voice_path = wav_path

                # Load audio
                waveform, sr = sf.read(wav_path)
                waveform     = torch.tensor(waveform).float()

                if waveform.ndim == 2:
                    waveform = waveform.mean(dim=1)

                waveform = waveform.flatten()

                if waveform.numel() == 0:
                    flash("Empty audio detected!", "danger")
                    return render_template("signUp.html")

                audio_tensor = waveform / (waveform.abs().max() + 1e-6)

                # Speaker embedding
                embedding = get_speaker_embedding(audio_tensor)

                if embedding is None:
                    flash("No clear speech detected!", "danger")
                    return render_template("signUp.html")

                voice_embedding = embedding.cpu().numpy().tolist()

            except Exception as e:
                print("VOICE ERROR:", str(e))
                flash(f"Voice processing error: {str(e)}", "danger")
                return render_template("signUp.html")

        # -----------------------
        # Save student to DB
        # -----------------------
        db.add_student(
            connection=connection,
            username=username,
            password=password,
            stu_id=stu_id,
            email=email,
            contact=phone,
            level=level,
            department=department,
            profile_image=face_path,
            voice_intro=voice_path,
            voice_embedding=voice_embedding,
            face_encoding=face_encoding
        )

        flash("Registration successful!", "success")
        return redirect(url_for('login'))

    return render_template("signUp.html")



from flask import request


@app.route('/verify_face', methods=['POST'])
@enforce_single_device
def verify_face_route():
    import os
    import base64

    # Base path to your project static folder
    BASE_STATIC = r"static"

    # Get image from front-end
    img_data = request.form['exam_image']

    # Remove base64 header
    img_str = img_data.split(',')[1]
    img_bytes = base64.b64decode(img_str)

    # Save exam image
    exam_dir = os.path.join(BASE_STATIC, "faces", "exam")
    os.makedirs(exam_dir, exist_ok=True)  # Ensure directory exists
    exam_path = os.path.join(exam_dir, f"{session['id']}_exam.jpg")
    with open(exam_path, 'wb') as f:
        f.write(img_bytes)

    # Path to saved user image
    saved_dir = os.path.join(BASE_STATIC, "faces", "cropped")
    saved_path = os.path.join(saved_dir, f"{session['id']}.jpg")

    # Verify face using ArcFace
    verified = verify_arcface(saved_path, exam_path)

    from flask import jsonify

    if verified:
        session["face_verified"] = True
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "fail"})


@app.route('/verify_face_page', methods=['GET'])
@enforce_single_device
def verify_face_page():
    if 'username' not in session:
        return redirect(url_for('login'))

    return render_template('verify_face.html', username=session['username'])


# 1. Route to start the process: Saves Exam ID and goes to Face Verification
@app.route('/start_exam_flow/<int:exam_id>', methods=['GET'])
@enforce_single_device
def start_exam_flow(exam_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    # Verify the exam exists and the student is eligible
    exam = connection.execute(
        "SELECT * FROM exams WHERE id=? AND status='published'", (exam_id,)
    ).fetchone()
    if not exam:
        flash("Exam not found or not available.", "danger")
        return redirect(url_for('index'))

    student = db.get_user(connection, session['username'])
    if student:
        import re as _re
        student_dept = student['department']
        _sl_match = _re.search(r'\d+', str(student['level']))
        student_level = _sl_match.group() if _sl_match else str(student['level'])
        exam_dept = exam['department']
        exam_level = str(exam['level'])
        if exam_dept != student_dept:
            flash("You are not eligible for this exam.", "danger")
            return redirect(url_for('index'))
        if exam_level != student_level:
            flash("You are not eligible for this exam.", "danger")
            return redirect(url_for('index'))

    # Save the exam ID in session so we remember it after the camera check
    session['current_exam_id'] = exam_id
    return redirect(url_for('verify_face_page'))


# 2. Route that loads the actual exam AFTER successful face verification
@app.route('/exam3', methods=['GET'])
@enforce_single_device
def take_exam_dynamic():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Retrieve the exam ID we saved in the previous step
    exam_id = session.get('current_exam_id')
    if not exam_id:
        flash("No exam selected. Please select an exam from the dashboard.", "danger")
        return redirect(url_for('index'))

    con = connection
    student = session['username']

    # Fetch Exam details
    exam = con.execute("SELECT * FROM exams WHERE id=? AND status='published'", (exam_id,)).fetchone()
    if not exam:
        flash("Exam not found or not available.", "danger")
        return redirect(url_for('index'))

    # Verify student is eligible for this exam
    _student = db.get_user(connection, student)
    if _student:
        import re as _re
        _s_dept = _student['department']
        _sl_match = _re.search(r'\d+', str(_student['level']))
        _s_level = _sl_match.group() if _sl_match else str(_student['level'])
        if exam['department'] != _s_dept:
            flash("You are not eligible for this exam.", "danger")
            return redirect(url_for('index'))
        if str(exam['level']) != _s_level:
            flash("You are not eligible for this exam.", "danger")
            return redirect(url_for('index'))

    # Check if student already submitted this exam
    existing = con.execute(
        "SELECT * FROM student_exams WHERE student_username=? AND exam_id=?",
        (student, exam_id)
    ).fetchone()
    if existing and existing['submitted_at']:
        flash("You have already submitted this exam.", "info")
        return redirect(url_for('index'))

    # Register the student for this exam if taking it for the first time
    if not existing:
        con.execute("INSERT INTO student_exams (student_username, exam_id) VALUES (?,?)", (student, exam_id))
        con.commit()

    # Fetch Questions
    questions = list(con.execute("SELECT * FROM exam_questions WHERE exam_id=?", (exam_id,)).fetchall())
    random.shuffle(questions)

    enriched = []
    for q in questions:
        opts = con.execute("SELECT * FROM exam_options WHERE question_id=? ORDER BY label", (q['id'],)).fetchall()
        q_dict = dict(q)
        enriched.append({
            'q': q_dict,
            'opts': [dict(o) for o in opts],
            'timer_secs': q_dict.get('timer_secs', 0) or 0,  # ← NEW
        })

    # Render the new dynamic BstartExam.html template
    return render_template('BstartExam.html',
                           exam=dict(exam), # exam.id
                           questions=enriched,
                           duration=exam['duration_mins'],
                           username=student)


@app.route('/analyze_audio', methods=['POST'])
def analyze_audio():
    try:
        audio_file = request.files['audio_data']
        webm_path = "temp_audio.webm"
        wav_path = "temp_audio.wav"
        audio_file.save(webm_path)

        # convert webm → wav using pydub
        from pydub import AudioSegment
        audio = AudioSegment.from_file(webm_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(wav_path, format="wav")

        import soundfile as sf
        y, sr = sf.read(wav_path)
        y = y.astype("float32")

        if y is None or len(y) < 512:
            return jsonify({"status": "no_speech"})

        audio_tensor = torch.from_numpy(y).float()
        exam_id = request.form.get("exam_id", "unknown")

        mean_embedding = db.get_student_voice_embedding(connection, session["id"])
        result = analyze_audio_chunk(audio_tensor, mean_embedding,
                                     session.get("same_speaker_count", 0),session["id"],exam_id)
        session["same_speaker_count"] = result["same_speaker_count"]

        print(f"[AUDIO] status={result['status']} score={float(result['score']):.3f}")
        return jsonify(result)

    except Exception as e:
        print(f"[AUDIO ROUTE ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "no_speech"})
    finally:
        if os.path.exists(webm_path):
            os.remove(webm_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)

import requests as http_requests  # pip install requests  (in Flask venv)

CV_SERVICE_URL = "http://127.0.0.1:5001"  # CV service runs here



@app.route('/analyze_frame', methods=['POST'])
@enforce_single_device
def analyze_frame():
    """Proxy: receives frame, verifies face locally, forwards to CV service."""
    if 'username' not in session:
        return jsonify({"error": "unauthorized"}), 401

    frame_file = request.files.get("frame")
    if not frame_file:
        return jsonify({"error": "no frame"}), 400

    frame_bytes = frame_file.read()

    # 1. Rely completely on the Session (the correct and most secure method)
    student_id = session.get("id")
    exam_id = request.form.get("exam_id", "unknown")

    # 2. Fetch the student's saved profile/ID face image
    saved_face_path = os.path.join("static", "faces", "cropped", f"{student_id}.jpg")

    # 3. Verify identity (ArcFace)
    is_match = verify_arcface_live(saved_face_path, frame_bytes)

    # =========================================================
    # NEW: CAPTURE EVIDENCE IF IDENTITY MISMATCH
    # =========================================================
    # Check explicitly for False so we ignore 'None' (empty chair)
    if is_match is False:
        evidence_dir = os.path.join(f"evidence_{student_id}_{exam_id}")
        os.makedirs(evidence_dir, exist_ok=True)

        count = len([
            f for f in os.listdir(evidence_dir)
            if f.startswith(f"mismatch_{student_id}")
        ]) + 1

        filename = f"mismatch_{student_id}_{count}.jpg"
        filepath = os.path.join(evidence_dir, filename)

        with open(filepath, "wb") as f:
            f.write(frame_bytes)

        import csv as _csv
        mismatch_csv_path = os.path.join(evidence_dir, "mismatch_report.csv")
        file_exists = os.path.isfile(mismatch_csv_path)
        with open(mismatch_csv_path, "a", newline="", encoding="utf-8") as csvf:
            writer = _csv.writer(csvf)
            if not file_exists:
                writer.writerow(["Time", "Violation"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                "identity_mismatch"
            ])

    # =========================================================

    # 4. Forward the same frame to the external CV Service
    try:
        allowed_names = db.get_allowed_objects(connection, exam_id)
        allowed_objects_str = ",".join(allowed_names)
    except Exception:
        allowed_objects_str = ""

    try:
        resp = http_requests.post(
            f"{CV_SERVICE_URL}/analyze_frame",
            files={"frame": (frame_file.filename, frame_bytes, frame_file.content_type)},
            data={"student_id": str(student_id),
                  "exam_id": str(exam_id),
                  "allowed_objects": allowed_objects_str,
                  },
            timeout=12
        )
        cv_data = resp.json()
    except Exception as e:
        print(f"[CV SERVICE ERROR] {e}")
        cv_data = {
            "violations": [], "gaze": "", "hand_sign": False,
            "extra_person": False, "out_of_frame": False
        }

    cv_data["face_match"] = bool(is_match)

    return jsonify(cv_data)

@app.route('/end_exam_cv', methods=['POST'])
@enforce_single_device
def end_exam_cv():
    """Tell CV service to flush and close the student's session CSV."""
    try:
        http_requests.post(f"{CV_SERVICE_URL}/end_session",
                           data={"student_id": str(session["id"])}, timeout=3)
    except Exception:
        pass
    return jsonify({"status": "ok"})


# =============================================================================
# EXAM MANAGEMENT ROUTES  (added — no existing code was changed)
# =============================================================================

# ── admin_page alias — fixes url_for('admin_page') in verify_2fa ─────────────
@app.route('/admin-page')
@enforce_single_device
def admin_page():
    return redirect(url_for('admin_dashboard'))


# ── Teacher: dashboard ────────────────────────────────────────────────────────
@app.route('/admin_dashboard')
@enforce_single_device
def admin_dashboard():
    if session.get('role') != 'doctor':
        flash("Access Denied: This area is restricted to Authorized Doctors only.", "danger")
        return redirect(url_for('index'))
    con = connection
    teacher = session['username']
    exams = con.execute(
        "SELECT * FROM exams WHERE teacher_username=? ORDER BY created_at DESC", (teacher,)
    ).fetchall()
    published = sum(1 for e in exams if e['status'] == 'published')
    total_exams = len(exams)
    exam_ids = [e['id'] for e in exams]
    active_students = 0
    if exam_ids:
        ph = ','.join('?' * len(exam_ids))
        active_students = con.execute(
            f"SELECT COUNT(*) FROM student_exams WHERE exam_id IN ({ph}) AND submitted_at IS NULL",
            exam_ids
        ).fetchone()[0]
    return render_template('admin_dashboard.html',
                           teacher_name=teacher,
                           exams=exams,
                           published=published,
                           total_exams=total_exams,
                           active_students=active_students,
                           flagged_today=0,
                           )


# ── Teacher: create exam page ─────────────────────────────────────────────────
# DB migration note:
#   ALTER TABLE exam_questions ADD COLUMN timer_secs   INTEGER DEFAULT 0;
@app.route('/create-exam')
@enforce_single_device
def create_exam():
    con = connection
    teacher = session['username']
    past_exams = con.execute(
        "SELECT id, title, course_code FROM exams WHERE teacher_username=? ORDER BY created_at DESC",
        (teacher,)
    ).fetchall()
    reuse_questions = []
    reuse_id = request.args.get('reuse')
    if reuse_id:
        reuse_questions = _load_exam_questions(con, int(reuse_id), teacher)
    return render_template('create-exam.html',
                           teacher_name=teacher,
                           past_exams=past_exams,
                           reuse_questions=reuse_questions,
                           )


# ── Teacher: save exam via fetch() ────────────────────────────────────────────
@app.route('/save-exam', methods=['POST'])
@enforce_single_device
def save_exam():
    data = request.get_json()
    print("[SAVE-EXAM] objects received:", data.get('objects', []))
    teacher = session['username']
    action = data.get('action', 'draft')
    status = 'published' if action == 'publish' else 'draft'
    proc = data.get('proctoring', {})
    con = connection
    exam_id = data.get('exam_id')

    # ── locking_mode replaces per-question no_backtrack ──
    locking_mode = int(data.get('locking_mode', 0))

    fields = (
        data.get('title', 'Untitled Exam'),
        data.get('course_code', ''),
        data.get('department', ''),
        int(data.get('level', 1)),
        data.get('start_datetime', ''),
        int(data.get('duration_mins', 90)),
        int(data.get('total_marks', 100)),
        int(data.get('passing_score', 60)),
        data.get('instructions', ''),
        data.get('warning_message', ''),
        status,
        int(proc.get('webcam', 1)),
        int(proc.get('face', 1)),
        int(proc.get('gaze', 1)),
        int(proc.get('audio', 1)),
        int(proc.get('tab', 1)),
        int(proc.get('phone', 1)),
        int(proc.get('multiface', 1)),
        locking_mode,
        teacher,
    )

    try:
        exam_id = db.upsert_exam(con, exam_id, fields, teacher)
        db.save_exam_objects(con, exam_id, data.get('objects', []))
        db.save_exam_questions(con, exam_id, teacher, data.get('questions', []))
        con.commit()
    except Exception as e:
        con.rollback()
        print("[SAVE-EXAM] ERROR:", e)
        import traceback; traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500

    return jsonify({'ok': True, 'exam_id': exam_id, 'status': status})

@app.route('/api/reuse-questions/<int:exam_id>')
@enforce_single_device
def api_reuse_questions(exam_id):
    con = connection
    teacher = session['username']
    exam = con.execute(
        "SELECT id FROM exams WHERE id=? AND teacher_username=?", (exam_id, teacher)
    ).fetchone()
    if not exam:
        return jsonify([]), 404
    result = _load_exam_questions(con, exam_id, teacher)
    return jsonify(result)


@app.route('/delete-exam/<int:exam_id>', methods=['POST'])
@enforce_single_device
def delete_exam(exam_id):
    connection.execute("DELETE FROM exams WHERE id=? AND teacher_username=?",
                       (exam_id, session['username']))
    connection.commit()
    return redirect(url_for('admin_dashboard'))


# ── Student: take exam (questions in random order) ───────────────────────────
# @app.route('/exam/<int:exam_id>', methods=['GET'])
# @enforce_single_device
# def take_exam(exam_id):
#     con = _exam_db()
#     student = session['username']
#     exam = con.execute(
#         "SELECT * FROM exams WHERE id=? AND status='published'", (exam_id,)
#     ).fetchone()
#     if not exam:
#         flash("Exam not found or not available.", "danger")
#         con.close()
#         return redirect(url_for('index'))
#
#     existing = con.execute(
#         "SELECT * FROM student_exams WHERE student_username=? AND exam_id=?",
#         (student, exam_id)
#     ).fetchone()
#     if existing and existing['submitted_at']:
#         flash("You have already submitted this exam.", "info")
#         con.close()
#         return redirect(url_for('index'))
#     if not existing:
#         con.execute(
#             "INSERT INTO student_exams (student_username, exam_id) VALUES (?,?)",
#             (student, exam_id)
#         )
#         con.commit()
#
#     questions = list(con.execute(
#         "SELECT * FROM exam_questions WHERE exam_id=?", (exam_id,)
#     ).fetchall())
#     random.shuffle(questions)
#
#     enriched = []
#     for q in questions:
#         opts = con.execute(
#             "SELECT * FROM exam_options WHERE question_id=? ORDER BY label", (q['id'],)
#         ).fetchall()
#         enriched.append({'q': dict(q), 'opts': [dict(o) for o in opts]})
#
#     con.close()
#     return render_template('exam.html',
#                            exam=dict(exam),
#                            questions=enriched,
#                            duration=exam['duration_mins'],
#                            )
#

# ── Student: submit exam ──────────────────────────────────────────────────────

@app.route('/submit-exam/<int:exam_id>', methods=['POST'])
@enforce_single_device
def submit_exam(exam_id):
    con = connection
    student = session['username']
    student_id = session['id']  # ← grab student_id from session

    se = con.execute(
        "SELECT * FROM student_exams WHERE student_username=? AND exam_id=?",
        (student, exam_id)
    ).fetchone()
    if not se or se['submitted_at']:
        return redirect(url_for('index'))

    exam = con.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    questions = con.execute("SELECT * FROM exam_questions WHERE exam_id=?", (exam_id,)).fetchall()
    score = 0
    total_possible = sum(q['points'] for q in questions)

    for q in questions:
        answer = request.form.get(f"q_{q['id']}", '')
        if q['question_type'] == 'short':
            con.execute(
                "INSERT INTO student_answers (student_exam_id,question_id,answer_text) VALUES (?,?,?)",
                (se['id'], q['id'], answer)
            )
        elif q['question_type'] == 'multi':
            selected_ids = request.form.getlist(f"q_{q['id']}")
            correct_opts = con.execute(
                "SELECT id FROM exam_options WHERE question_id=? AND is_correct=1", (q['id'],)
            ).fetchall()
            correct_ids = {str(o['id']) for o in correct_opts}
            correct = 1 if set(selected_ids) == correct_ids and len(selected_ids) > 0 else 0
            if correct:
                score += q['points']
            con.execute(
                "INSERT INTO student_answers (student_exam_id,question_id,answer_text,is_correct) VALUES (?,?,?,?)",
                (se['id'], q['id'], ','.join(sorted(selected_ids)) if selected_ids else None, correct)
            )
        else:
            opt = con.execute(
                "SELECT * FROM exam_options WHERE question_id=? AND id=?",
                (q['id'], answer)
            ).fetchone() if answer else None
            correct = 1 if (opt and opt['is_correct']) else 0
            if correct:
                score += q['points']
            con.execute(
                "INSERT INTO student_answers (student_exam_id,question_id,option_id,is_correct) VALUES (?,?,?,?)",
                (se['id'], q['id'], answer or None, correct)
            )

    pct = round(score / total_possible * 100) if total_possible else 0
    passed = 1 if pct >= exam['passing_score'] else 0
    con.execute(
        "UPDATE student_exams SET submitted_at=CURRENT_TIMESTAMP, score=?, passed=? WHERE id=?",
        (pct, passed, se['id'])
    )
    con.commit()

    # ── Cheating Risk Report ──────────────────────────────────────
    risk_results = None
    try:
        exam_duration_sec = exam['duration_mins'] * 60

        # Find the webcam CSV — folder format: evidence_{student_id}_{date}_{time}
        webcam_csv = None
        for folder_name in os.listdir("."):
            if folder_name.startswith(f"evidence_{student_id}") and os.path.isdir(folder_name):
                candidate = os.path.join(folder_name, "report.csv")
                if os.path.exists(candidate):
                    webcam_csv = candidate
                    break  # take the first match

        if webcam_csv:
            risk_results = generate_cheating_report(
                student_id=student_id,
                exam_id=exam_id,
                exam_duration_sec=exam_duration_sec
            )
            print(f"[RISK] Student {student_id} → "
                  f"{risk_results['risk_level']} "
                  f"({risk_results['combined_percentage']}%)")
        else:
            print(f"[RISK] No webcam CSV found for student {student_id}")

    except Exception as e:
        print(f"[RISK ERROR] {e}")
        import traceback
        traceback.print_exc()
    # ─────────────────────────────────────────────────────────────

    return render_template('exam_result.html',
                           exam=dict(exam),
                           score=pct,
                           passed=passed,
                           raw_score=score,
                           total_possible=total_possible,
                           risk=risk_results  # ← available in template if needed
                           )




# @app.route('/submit-exam/<int:exam_id>', methods=['POST'])
# @enforce_single_device
# def submit_exam(exam_id):
#     con = _exam_db()
#     student = session['username']
#     se = con.execute(
#         "SELECT * FROM student_exams WHERE student_username=? AND exam_id=?",
#         (student, exam_id)
#     ).fetchone()
#     if not se or se['submitted_at']:
#         con.close()
#         return redirect(url_for('index'))
#
#     exam = con.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
#     questions = con.execute("SELECT * FROM exam_questions WHERE exam_id=?", (exam_id,)).fetchall()
#     score = 0
#     total_possible = sum(q['points'] for q in questions)
#
#     for q in questions:
#         answer = request.form.get(f"q_{q['id']}", '')
#         if q['question_type'] == 'short':
#             con.execute(
#                 "INSERT INTO student_answers (student_exam_id,question_id,answer_text) VALUES (?,?,?)",
#                 (se['id'], q['id'], answer)
#             )
#         else:
#             opt = con.execute(
#                 "SELECT * FROM exam_options WHERE question_id=? AND id=?",
#                 (q['id'], answer)
#             ).fetchone() if answer else None
#             correct = 1 if (opt and opt['is_correct']) else 0
#             if correct:
#                 score += q['points']
#             con.execute(
#                 "INSERT INTO student_answers (student_exam_id,question_id,option_id,is_correct) VALUES (?,?,?,?)",
#                 (se['id'], q['id'], answer or None, correct)
#             )
#
#     pct = round(score / total_possible * 100) if total_possible else 0
#     passed = 1 if pct >= exam['passing_score'] else 0
#     con.execute(
#         "UPDATE student_exams SET submitted_at=CURRENT_TIMESTAMP, score=?, passed=? WHERE id=?",
#         (pct, passed, se['id'])
#     )
#     con.commit()
#     con.close()
#     return render_template('exam_result.html',
#                            exam=dict(exam),
#                            score=pct,
#                            passed=passed,
#                            raw_score=score,
#                            total_possible=total_possible,
#                            )
#

# ── Teacher: reports ──────────────────────────────────────────────────────────
@app.route('/report')
@enforce_single_device
def report():
    con = connection
    teacher = session['username']
    exams = con.execute(
        "SELECT * FROM exams WHERE teacher_username=? ORDER BY created_at DESC", (teacher,)
    ).fetchall()
    exam_stats = []
    for e in exams:
        rows = con.execute(
            "SELECT score, passed FROM student_exams WHERE exam_id=? AND submitted_at IS NOT NULL",
            (e['id'],)
        ).fetchall()
        n = len(rows)
        avg = round(sum(r['score'] for r in rows) / n, 1) if n else 0
        pass_n = sum(1 for r in rows if r['passed'])
        exam_stats.append({
            'exam': dict(e),
            'attempts': n,
            'avg': avg,
            'pass_rate': round(pass_n / n * 100) if n else 0,
        })
    return render_template('report.html',
                           teacher_name=teacher,
                           exam_stats=exam_stats,
                           )


# ── CV module: forbidden objects for an exam ──────────────────────────────────
@app.route('/api/exam-objects/<int:exam_id>', methods=['GET'])
@enforce_single_device
def api_exam_objects(exam_id):
    objects = connection.execute(
        "SELECT name, allowed FROM forbidden_objects WHERE exam_id=?", (exam_id,)
    ).fetchall()
    return jsonify([{'name': o['name'], 'allowed': bool(o['allowed'])} for o in objects])


import csv



@app.route('/log', methods=['POST'])
def log_event():
    data = request.get_json()

    event = data.get('event')
    student_id = session.get('id')
    exam_id = data.get('exam_id', 'unknown')  # ✅ ADD THIS
    username = session.get('username')

    print(f"[SECURITY ALERT] Student: {username} (ID: {student_id}) | Event: {event}")

    # Per-student system events file
    folder = os.path.join("static", "system_events")
    os.makedirs(folder, exist_ok=True)
    csv_file_path = os.path.join(folder, f"system_events_{student_id}_{exam_id}.csv")

    file_exists = os.path.isfile(csv_file_path)

    try:
        with open(csv_file_path, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)

            if not file_exists:
                writer.writerow(["Timestamp", "Exam ID", "Event"])

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([timestamp, event])

    except Exception as e:
        print(f"Error saving to CSV: {e}")

    return jsonify({"status": "logged"})


# @app.route('/log', methods=['POST'])
# # @enforce_single_device  <-- Keep your decorator if you are using it!
# def log_event():
#     data = request.get_json()
#
#     # 1. Get the event and student identity
#     event = data.get('event')
#     student_id = session.get('id')
#     username = session.get('username')
#
#     # 2. Print to terminal (so you can still see it live)
#     print(f"[SECURITY ALERT] Student: {username} (ID: {student_id}) | Event: {event}")
#
#     # 3. Save the violation to a CSV file
#     csv_file_path = "security_logs.csv"
#     file_exists = os.path.isfile(csv_file_path)  # Check if file exists to write headers
#
#     try:
#         with open(csv_file_path, mode='a', newline='', encoding='utf-8') as file:
#             writer = csv.writer(file)
#
#             # If the file is brand new, write the column headers first
#             if not file_exists:
#                 writer.writerow(["Timestamp", "Student_ID", "Username", "Event"])
#
#             # Get the exact time the cheating was attempted
#             timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#
#             # Write the student's data as a new row
#             writer.writerow([timestamp, student_id, username, event])
#
#     except Exception as e:
#         print(f"Error saving to CSV: {e}")
#
#     return jsonify({"status": "logged"})

# =============================================================================
# END OF ADDED ROUTES
# =============================================================================


import os
import csv


# @app.route('/report')
# def report():
#     if session.get('role') != 'doctor':
#         return redirect(url_for('index'))
#
#     all_reports = []
#     reports_base_dir = os.path.join("static", "reports")
#
#     if os.path.exists(reports_base_dir):
#         # Loop through every folder in static/reports/
#         for folder_name in os.listdir(reports_base_dir):
#             if folder_name.startswith("report_"):
#                 # Extract student_id and exam_id from folder name
#                 # folder_name is "report_123_456"
#                 parts = folder_name.split('_')
#                 if len(parts) == 3:
#                     stu_id = parts[1]
#                     ex_id = parts[2]
#
#                     summary_path = os.path.join(reports_base_dir, folder_name, "risk_summary.csv")
#
#                     if os.path.exists(summary_path):
#                         report_data = {
#                             "student_id": stu_id,
#                             "exam_id": ex_id,
#                             "risk_level": "Unknown",
#                             "total_violations": 0
#                         }
#                         # Read the summary data
#                         with open(summary_path, mode="r") as f:
#                             for row in csv.DictReader(f):
#                                 if row["metric"] == "risk_level":
#                                     report_data["risk_level"] = row["value"]
#                                 if row["metric"] == "suspicious_count":
#                                     report_data["total_violations"] = row["value"]
#
#                         all_reports.append(report_data)
#
#     return render_template('all_reports.html', reports=all_reports)


@app.route('/exam-students/<int:exam_id>')
@enforce_single_device
def exam_students(exam_id):
    if session.get('role') != 'doctor':
        return redirect(url_for('index'))

    con = connection
    exam = con.execute("SELECT * FROM exams WHERE id=?", (exam_id,)).fetchone()
    students = con.execute("""
        SELECT * FROM student_exams WHERE exam_id=? ORDER BY submitted_at DESC
    """, (exam_id,)).fetchall()

    students_data = []
    for s in students:
        user   = db.get_user(connection, s['student_username'])
        stu_id = user[3] if user else None

        # Read risk level from summary file
        risk_level = None
        report_exists = False
        if stu_id:
            summary_path = os.path.join("static", "reports",
                                        f"report_{stu_id}_{exam_id}", "risk_summary.csv")
            if os.path.exists(summary_path):
                report_exists = True
                with open(summary_path, mode="r") as f:
                    for row in csv.DictReader(f):
                        if row["metric"] == "risk_level":
                            risk_level = row["value"]
                            break

        students_data.append({
            "username":      s['student_username'],
            "student_id":    stu_id,
            "score":         s['score'],
            "passed":        s['passed'],
            "submitted_at":  s['submitted_at'],
            "report_exists": report_exists,
            "risk_level":    risk_level
        })

    return render_template('exam_students.html',
                           exam=dict(exam),
                           students=students_data)

from flask import send_from_directory
import os

@app.route('/get-evidence/<folder>/<filename>')
def get_evidence(folder, filename):
    # This points to the folder sitting next to app.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(base_dir, folder)
    return send_from_directory(folder_path, filename)

@app.route('/view-report/<int:student_id>/<int:exam_id>')
@enforce_single_device
def view_report(student_id, exam_id):
    if session.get('role') != 'doctor':
        return redirect(url_for('index'))

    # Get the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Path to the folder in the project root
    evidence_folder_name = f"evidence_{student_id}_{exam_id}"
    evidence_dir = os.path.join(project_root, evidence_folder_name)

    # Debugging: Check your terminal to see if this is "True"
    print(f"Checking for evidence in: {evidence_dir} | Exists: {os.path.exists(evidence_dir)}")

    summary_file = os.path.join("static", "reports", f"report_{student_id}_{exam_id}", "risk_summary.csv")
    audio_file = os.path.join("static", "suspicious_events", f"suspicious_events_{student_id}_{exam_id}.csv")
    system_file = os.path.join("static", "system_events", f"system_events_{student_id}_{exam_id}.csv")

    # 1. Load Risk Summary
    risk_summary = {}
    if os.path.exists(summary_file):
        with open(summary_file, mode="r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                risk_summary[row.get("metric", "")] = row.get("value", "0")

    # 2. Load Audio Events
    audio_events = []
    if os.path.exists(audio_file):
        with open(audio_file, mode="r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                audio_events.append({
                    'timestamp': row.get('timestamp') or row.get('Timestamp') or '—',
                    'event_label': row.get('event_label') or 'Unknown',
                    'duration_sec': row.get('duration_sec') or '0'
                })

    # 3. Load System Events
    system_events = []
    if os.path.exists(system_file):
        with open(system_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 2:
                    ts, evt = row[0].strip(), row[1].strip()
                    clean_class = evt.replace(' ', '-').replace('&', 'and')
                    system_events.append({
                        'Timestamp': ts,
                        'Event': evt,
                        'Class': clean_class
                    })

    # 4. Load ALL Evidence Images (Looping through every file)
    all_evidence_images = []
    if os.path.exists(evidence_dir):
        try:
            # Grab every image in the folder regardless of prefix (obj_ or gaze_)
            all_files = os.listdir(evidence_dir)
            all_evidence_images = [f for f in all_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            all_evidence_images.sort()
            print(f"Found {len(all_evidence_images)} images.")
        except Exception as e:
            print(f"Error reading directory: {e}")

    return render_template('view_report.html',
                           student_id=student_id,
                           exam_id=exam_id,
                           risk_summary=risk_summary,
                           audio_events=audio_events,
                           system_events=system_events,
                           obj_images=all_evidence_images,
                           evidence_folder=evidence_folder_name)

# @app.route('/view-report/<int:student_id>/<int:exam_id>')
# @enforce_single_device
# def view_report(student_id, exam_id):
#     if session.get('role') != 'doctor':
#         return redirect(url_for('index'))
#
#     project_root = os.path.dirname(os.path.abspath(__file__))
#
#     summary_file = os.path.join("static", "reports", f"report_{student_id}_{exam_id}", "risk_summary.csv")
#     audio_file   = os.path.join("static", "suspicious_events", f"suspicious_events_{student_id}_{exam_id}.csv")
#     system_file  = os.path.join("static", "system_events",     f"system_events_{student_id}_{exam_id}.csv")
#     evidence_dir = os.path.join(project_root, f"evidence_{student_id}_{exam_id}")
#
#     risk_summary = {}
#     if os.path.exists(summary_file):
#         with open(summary_file, mode="r") as f:
#             for row in csv.DictReader(f):
#                 risk_summary[row["metric"]] = row["value"]
#
#     audio_events = []
#     if os.path.exists(audio_file):
#         with open(audio_file, mode="r") as f:
#             audio_events = list(csv.DictReader(f))
#
#     system_events = []
#     if os.path.exists(system_file):
#         with open(system_file, mode="r") as f:
#             system_events = list(csv.DictReader(f))
#
#     obj_images  = []
#     gaze_images = []
#     if os.path.exists(evidence_dir):
#         all_files   = os.listdir(evidence_dir)
#         obj_images  = [f for f in all_files if f.startswith("obj_")  and f.endswith(".jpg")]
#         gaze_images = [f for f in all_files if f.startswith("gaze_") and f.endswith(".jpg")]
#
#     return render_template('view_report.html',
#                            student_id=student_id,
#                            exam_id=exam_id,
#                            risk_summary=risk_summary,
#                            audio_events=audio_events,
#                            system_events=system_events,
#                            obj_images=obj_images,
#                            gaze_images=gaze_images,
#                            evidence_folder=f"evidence_{student_id}_{exam_id}")


@app.route('/evidence/<path:filename>')
@enforce_single_device
def serve_evidence(filename):
    if session.get('role') != 'doctor':
        return redirect(url_for('index'))
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), filename)

@app.route('/all-ai-reports') # Change the URL slightly
@enforce_single_device
def all_ai_reports():        # Change the function name
    if session.get('role') != 'doctor':
        flash("Access Denied: This area is restricted to Authorized Doctors only.", "danger")
        return redirect(url_for('index'))

    all_reports = []
    reports_base_dir = os.path.join("static", "reports")

    if os.path.exists(reports_base_dir):
        for folder_name in os.listdir(reports_base_dir):
            if folder_name.startswith("report_"):
                parts = folder_name.split('_')
                if len(parts) == 3:
                    stu_id, ex_id = parts[1], parts[2]
                    summary_path = os.path.join(reports_base_dir, folder_name, "risk_summary.csv")

                    if os.path.exists(summary_path):
                        report_data = {"student_id": stu_id, "exam_id": ex_id, "risk_level": "Unknown", "total_violations": 0}
                        with open(summary_path, mode="r") as f:
                            for row in csv.DictReader(f):
                                if row["metric"] == "risk_level": report_data["risk_level"] = row["value"]
                                if row["metric"] == "suspicious_count": report_data["total_violations"] = row["value"]
                        all_reports.append(report_data)

    return render_template('all_reports.html', reports=all_reports)


if __name__ == '__main__':
    db.init_db(connection)
    # evaluate_pairs(PAIRS_FILE, LFW_PATH)
    app.run(debug=True, port=5050)

