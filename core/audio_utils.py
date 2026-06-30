# # # the audio config
# # import torch
# # import sounddevice as sd
# # import tkinter as tk
# # import matplotlib.pyplot as plt
# # from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# # from speechbrain.inference import EncoderClassifier
# #
# #
# #
# # # ================================
# # # CONFIG
# # # ================================
# # SAMPLING_RATE = 16000
# # BLOCK_SIZE = 1024
# # ENROLL_SECONDS = 8
# # MONITOR_SECONDS = 5
# # SPEECH_MIN_LENGTH = 1.0
# # SIMILARITY_THRESHOLD = 0.4
# # CHUNK_SECONDS = 3
# #
# # # ================================
# # # LOAD SPEAKER MODEL (SpeechBrain ECAPA)
# # # ================================
# # # spk_model = EncoderClassifier.from_hparams(
# # #     source="speechbrain/spkrec-ecapa-voxceleb",
# # #     run_opts={"device": "cpu"}
# # # )
# # # NEW
# # spk_model = EncoderClassifier.from_hparams(
# #     source="speechbrain/spkrec-ecapa-voxceleb",
# #     run_opts={"device": "cpu"},
# #     savedir="pretrained_models/spkrec-ecapa-voxceleb"
# # )
# # # ================================
# # # LOAD SILERO VAD
# # # ================================
# # vad_model, utilss = torch.hub.load(
# #     repo_or_dir="snakers4/silero-vad",
# #     model="silero_vad",
# #     trust_repo=True
# # )
# #
# # (get_speech_timestamps, _, _, _, _) = utilss
# #
# #
# # def record_audio(seconds=ENROLL_SECONDS):
# #     print(f"Recording {seconds} seconds...")
# #     recording = sd.rec(int(seconds * SAMPLING_RATE), samplerate=SAMPLING_RATE, channels=1, dtype='float32')
# #     sd.wait()
# #     return recording.flatten()
# #
# # def apply_vad(audio_tensor):
# #     #----------------------------->
# #     # ── ADD THESE 4 LINES ──────────────────────────────────────────
# #     MIN_SAMPLES = 512   # Silero VAD minimum chunk size at 16kHz
# #     if audio_tensor.shape[-1] < MIN_SAMPLES:
# #
# #         audio_tensor = torch.nn.functional.pad(audio_tensor, (0, MIN_SAMPLES - audio_tensor.shape[-1]))
# #     # ───────────────────────────────────────────────────────────────
# #
# #     #------------------------------?
# #     speech_timestamps = get_speech_timestamps(
# #         audio_tensor,
# #         vad_model,
# #         sampling_rate=SAMPLING_RATE,
# #         threshold=0.4
# #     )
# #
# #     if len(speech_timestamps) == 0:
# #         return None
# #
# #     segments = []
# #     for seg in speech_timestamps:
# #         segments.append(audio_tensor[seg["start"]:seg["end"]])
# #
# #     speech = torch.cat(segments)
# #
# #     if speech.shape[0] < SPEECH_MIN_LENGTH * SAMPLING_RATE:
# #         return None
# #
# #     return speech
# #
# #
# #
# # def get_speaker_embedding(audio_tensor):
# #     """
# #     Given a raw audio tensor, applies VAD, splits into chunks,
# #     encodes each chunk with the speaker model, and returns the
# #     mean normalized embedding.
# #
# #     Returns:
# #         torch.Tensor or None: mean embedding of the speaker, or None if no speech
# #     """
# #     # Apply VAD
# #     speech = apply_vad(audio_tensor)
# #     if speech is None:
# #         return None  # No speech detected
# #
# #     student_embeddings = []
# #     chunk_size = SAMPLING_RATE * CHUNK_SECONDS
# #     chunks = speech.split(chunk_size)
# #
# #     with torch.no_grad():
# #         for chunk in chunks:
# #             if len(chunk) > SAMPLING_RATE:
# #                 emb = spk_model.encode_batch(chunk.unsqueeze(0))
# #                 emb = emb.squeeze()
# #                 emb = emb / torch.norm(emb)  # normalize
# #                 student_embeddings.append(emb)
# #
# #     if not student_embeddings:
# #         return None
# #
# #     mean_embedding = torch.mean(torch.stack(student_embeddings), dim=0)
# #     mean_embedding = mean_embedding / torch.norm(mean_embedding)
# #     return mean_embedding
# #
# #
#
#
#
#
#
#
#
# import torch
# import torchaudio
# import sounddevice as sd
# import numpy as np
# import os
# import csv
# from datetime import datetime
# from speechbrain.inference import EncoderClassifier
#
# # ================================
# # CONFIG
# # ================================
# SAMPLING_RATE = 16000
# BLOCK_SIZE = 1024
# ENROLL_SECONDS = 8
# MONITOR_SECONDS = 5
# SPEECH_MIN_LENGTH = 1.0
# SIMILARITY_THRESHOLD = 0.3
# CHUNK_SECONDS = 2
# SAME_SPEAKER_LIMIT = 3
#
# # ================================
# # CSV LOGGING
# # ================================
# CSV_FILE = "suspicious_events.csv"
#
# with open(CSV_FILE, mode="w", newline="") as f:
#     csv.writer(f).writerow(["timestamp", "duration_sec", "event_label"])
#
#
# def log_suspicious_event(duration_sec, event_label):
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     with open(CSV_FILE, mode="a", newline="") as f:
#         csv.writer(f).writerow([timestamp, duration_sec, event_label])
#
#
# # ================================
# # LAZY MODEL LOADING
# # ================================
# _spk_model = None
# _vad_model = None
# _get_speech_timestamps = None
# _osd_pipeline = None
#
#
# def get_spk_model():
#     global _spk_model
#     if _spk_model is None:
#         _spk_model = EncoderClassifier.from_hparams(
#             source="speechbrain/spkrec-ecapa-voxceleb",
#             run_opts={"device": "cpu"},
#             savedir="pretrained_models/spkrec-ecapa-voxceleb"
#         )
#     return _spk_model
#
#
# def get_vad_model():
#     global _vad_model, _get_speech_timestamps
#     if _vad_model is None:
#         _vad_model, utils = torch.hub.load(
#             repo_or_dir="snakers4/silero-vad",
#             model="silero_vad",
#             trust_repo=True
#         )
#         (_get_speech_timestamps, _, _, _, _) = utils
#     return _vad_model, _get_speech_timestamps
#
#
# def get_osd_pipeline():
#     global _osd_pipeline
#     if _osd_pipeline is None:
#         # Patch torch.load for pyannote compatibility
#         _original_torch_load = torch.load
#
#         def patched_torch_load(*args, **kwargs):
#             kwargs["weights_only"] = False
#             return _original_torch_load(*args, **kwargs)
#
#         torch.load = patched_torch_load
#
#         from pyannote.audio import Pipeline
#         HF_TOKEN = os.environ.get("HF_TOKEN", "HF_TOKEN_PLACEHOLDER")
#         _osd_pipeline = Pipeline.from_pretrained(
#             "pyannote/overlapped-speech-detection",
#             token=HF_TOKEN
#         )
#     return _osd_pipeline
#
#
# # ================================
# # VAD
# # ================================
# def apply_vad(audio_tensor):
#     vad_model, get_speech_timestamps = get_vad_model()
#
#     MIN_SAMPLES = 512
#     if audio_tensor.shape[-1] < MIN_SAMPLES:
#         audio_tensor = torch.nn.functional.pad(
#             audio_tensor, (0, MIN_SAMPLES - audio_tensor.shape[-1])
#         )
#
#     speech_timestamps = get_speech_timestamps(
#         audio_tensor,
#         vad_model,
#         sampling_rate=SAMPLING_RATE,
#         threshold=0.4
#     )
#
#     if len(speech_timestamps) == 0:
#         return None
#
#     segments = []
#     for seg in speech_timestamps:
#         segments.append(audio_tensor[seg["start"]:seg["end"]])
#
#     if len(segments) == 0:
#         return None
#
#     speech = torch.cat(segments)
#
#     if speech.shape[0] < SPEECH_MIN_LENGTH * SAMPLING_RATE:
#         return None
#
#     return speech
#
#
# # ================================
# # OVERLAP DETECTION
# # ================================
# # def detect_overlap(audio_tensor):
# #     """Returns True if overlapping speech detected."""
# #     try:
# #         pipeline = get_osd_pipeline()
# #         temp_file = "temp_overlap.wav"
# #         torchaudio.save(temp_file, audio_tensor.unsqueeze(0), SAMPLING_RATE)
# #         output = pipeline(temp_file)
# #         for segment, _, label in output.itertracks(yield_label=True):
# #             if label == "OVERLAP":
# #                 return True
# #     except Exception as e:
# #         print(f"[OVERLAP] Error: {e}")
# #     return False
#
# def detect_overlap(audio_tensor):
#     try:
#         pipeline = get_osd_pipeline()
#         temp_file = "temp_overlap.wav"
#         torchaudio.save(temp_file, audio_tensor.unsqueeze(0), SAMPLING_RATE)
#         output = pipeline(temp_file)
#
#         # ── print ALL segments to see what pyannote actually returns
#         print("[OVERLAP] all segments:")
#         for segment, _, label in output.itertracks(yield_label=True):
#             print(f"  segment={segment}, label={label}")
#
#         # check for overlap
#         for segment, _, label in output.itertracks(yield_label=True):
#             if label == "OVERLAP":
#                 return True
#
#     except Exception as e:
#         print(f"[OVERLAP] Error: {e}")
#
#     print("[OVERLAP] no overlap found")
#     return False
# # ================================
# # SPEAKER EMBEDDING
# # ================================
# def get_speaker_embedding(audio_tensor):
#     """
#     Applies VAD, splits into chunks, encodes each chunk,
#     returns mean normalized embedding or None if no speech.
#     """
#     speech = apply_vad(audio_tensor)
#     if speech is None:
#         return None
#
#     spk_model = get_spk_model()
#     student_embeddings = []
#     chunk_size = SAMPLING_RATE * CHUNK_SECONDS
#     chunks = speech.split(chunk_size)
#
#     with torch.no_grad():
#         for chunk in chunks:
#             if len(chunk) > SAMPLING_RATE:
#                 emb = spk_model.encode_batch(chunk.unsqueeze(0))
#                 emb = emb.squeeze()
#                 emb = emb / torch.norm(emb)
#                 student_embeddings.append(emb)
#
#     if not student_embeddings:
#         return None
#
#     mean_embedding = torch.mean(torch.stack(student_embeddings), dim=0)
#     mean_embedding = mean_embedding / torch.norm(mean_embedding)
#     return mean_embedding
#
#
# # ================================
# # FULL MONITORING ANALYSIS
# # (called by Flask /analyze_audio route)
# # ================================
# def analyze_audio_chunk(audio_tensor, mean_embedding, same_speaker_count):
#     """
#     Runs full analysis: VAD → overlap check → speaker check.
#
#     Returns dict:
#         status: "no_speech" | "overlap" | "same_speaker" | "different_speaker"
#         score: float (cosine similarity, if speaker check ran)
#         same_speaker_count: updated count
#         duration_sec: float
#     """
#     speech = apply_vad(audio_tensor)
#
#     if speech is None:
#         return {"status": "no_speech", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": 0}
#
#     if speech.shape[0] < SAMPLING_RATE:
#         return {"status": "no_speech", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": 0}
#
#     duration_sec = len(speech) / SAMPLING_RATE
#
#     # ── 1. Overlap check ─────────────────────────────────────────
#     if detect_overlap(speech):
#         log_suspicious_event(duration_sec, "OVERLAP")
#         return {"status": "overlap", "score": 0,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}
#
#     # ── 2. Speaker check ─────────────────────────────────────────
#     if mean_embedding is None:
#         return {"status": "no_enrollment", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": duration_sec}
#
#     spk_model = get_spk_model()
#     with torch.no_grad():
#         emb = spk_model.encode_batch(speech.unsqueeze(0))
#         emb = emb.squeeze()
#         emb = emb / torch.norm(emb)
#
#     mean_embedding = torch.tensor(mean_embedding) if not isinstance(
#         mean_embedding, torch.Tensor) else mean_embedding
#
#     similarity = torch.cosine_similarity(emb, mean_embedding, dim=0).item()
#
#     if similarity >= SIMILARITY_THRESHOLD:
#         same_speaker_count += 1
#         if same_speaker_count >= SAME_SPEAKER_LIMIT:
#             log_suspicious_event(duration_sec, "SAME_PERSON_TOO_MUCH")
#             same_speaker_count = 0
#             return {"status": "same_speaker_suspicious", "score": similarity,
#                     "same_speaker_count": same_speaker_count,
#                     "duration_sec": duration_sec}
#         return {"status": "same_speaker", "score": similarity,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}
#     else:
#         log_suspicious_event(duration_sec, "DIFFERENT_SPEAKER")
#         return {"status": "different_speaker", "score": similarity,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}
#
#
#
#


# # the audio config
# import torch
# import sounddevice as sd
# import tkinter as tk
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from speechbrain.inference import EncoderClassifier
#
#
#
# # ================================
# # CONFIG
# # ================================
# SAMPLING_RATE = 16000
# BLOCK_SIZE = 1024
# ENROLL_SECONDS = 8
# MONITOR_SECONDS = 5
# SPEECH_MIN_LENGTH = 1.0
# SIMILARITY_THRESHOLD = 0.4
# CHUNK_SECONDS = 3
#
# # ================================
# # LOAD SPEAKER MODEL (SpeechBrain ECAPA)
# # ================================
# # spk_model = EncoderClassifier.from_hparams(
# #     source="speechbrain/spkrec-ecapa-voxceleb",
# #     run_opts={"device": "cpu"}
# # )
# # NEW
# spk_model = EncoderClassifier.from_hparams(
#     source="speechbrain/spkrec-ecapa-voxceleb",
#     run_opts={"device": "cpu"},
#     savedir="pretrained_models/spkrec-ecapa-voxceleb"
# )
# # ================================
# # LOAD SILERO VAD
# # ================================
# vad_model, utilss = torch.hub.load(
#     repo_or_dir="snakers4/silero-vad",
#     model="silero_vad",
#     trust_repo=True
# )
#
# (get_speech_timestamps, _, _, _, _) = utilss
#
#
# def record_audio(seconds=ENROLL_SECONDS):
#     print(f"Recording {seconds} seconds...")
#     recording = sd.rec(int(seconds * SAMPLING_RATE), samplerate=SAMPLING_RATE, channels=1, dtype='float32')
#     sd.wait()
#     return recording.flatten()
#
# def apply_vad(audio_tensor):
#     #----------------------------->
#     # ── ADD THESE 4 LINES ──────────────────────────────────────────
#     MIN_SAMPLES = 512   # Silero VAD minimum chunk size at 16kHz
#     if audio_tensor.shape[-1] < MIN_SAMPLES:
#
#         audio_tensor = torch.nn.functional.pad(audio_tensor, (0, MIN_SAMPLES - audio_tensor.shape[-1]))
#     # ───────────────────────────────────────────────────────────────
#
#     #------------------------------?
#     speech_timestamps = get_speech_timestamps(
#         audio_tensor,
#         vad_model,
#         sampling_rate=SAMPLING_RATE,
#         threshold=0.4
#     )
#
#     if len(speech_timestamps) == 0:
#         return None
#
#     segments = []
#     for seg in speech_timestamps:
#         segments.append(audio_tensor[seg["start"]:seg["end"]])
#
#     speech = torch.cat(segments)
#
#     if speech.shape[0] < SPEECH_MIN_LENGTH * SAMPLING_RATE:
#         return None
#
#     return speech
#
#
#
# def get_speaker_embedding(audio_tensor):
#     """
#     Given a raw audio tensor, applies VAD, splits into chunks,
#     encodes each chunk with the speaker model, and returns the
#     mean normalized embedding.
#
#     Returns:
#         torch.Tensor or None: mean embedding of the speaker, or None if no speech
#     """
#     # Apply VAD
#     speech = apply_vad(audio_tensor)
#     if speech is None:
#         return None  # No speech detected
#
#     student_embeddings = []
#     chunk_size = SAMPLING_RATE * CHUNK_SECONDS
#     chunks = speech.split(chunk_size)
#
#     with torch.no_grad():
#         for chunk in chunks:
#             if len(chunk) > SAMPLING_RATE:
#                 emb = spk_model.encode_batch(chunk.unsqueeze(0))
#                 emb = emb.squeeze()
#                 emb = emb / torch.norm(emb)  # normalize
#                 student_embeddings.append(emb)
#
#     if not student_embeddings:
#         return None
#
#     mean_embedding = torch.mean(torch.stack(student_embeddings), dim=0)
#     mean_embedding = mean_embedding / torch.norm(mean_embedding)
#     return mean_embedding
#
#







import torch
import torchaudio
import sounddevice as sd
import numpy as np
import os
import csv
from datetime import datetime
from speechbrain.inference import EncoderClassifier

# ================================
# CONFIG
# ================================
SAMPLING_RATE = 16000
BLOCK_SIZE = 1024
ENROLL_SECONDS = 8
MONITOR_SECONDS = 5
SPEECH_MIN_LENGTH = 1.0
SIMILARITY_THRESHOLD = 0.23
CHUNK_SECONDS = 2
SAME_SPEAKER_LIMIT = 3

# ================================
# CSV LOGGING
# ================================
# CSV_FILE = "suspicious_events.csv"
#
# with open(CSV_FILE, mode="w", newline="") as f:
#     csv.writer(f).writerow(["timestamp", "duration_sec", "event_label"])
#
#
# def log_suspicious_event(duration_sec, event_label):
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#     with open(CSV_FILE, mode="a", newline="") as f:
#         csv.writer(f).writerow([timestamp, duration_sec, event_label])


import os


def init_student_csv(student_id, exam_id):
    """Initialize CSV file for a specific student and exam."""
    folder = os.path.join("static", "suspicious_events")
    os.makedirs(folder, exist_ok=True)

    # Include exam_id in the filename
    csv_file = os.path.join(folder, f"suspicious_events_{student_id}_{exam_id}.csv")

    with open(csv_file, mode="w", newline="") as f:
        csv.writer(f).writerow(["timestamp", "duration_sec", "event_label"])

    return csv_file


def log_suspicious_event(student_id, exam_id, duration_sec, event_label):
    folder = os.path.join("static", "suspicious_events")
    os.makedirs(folder, exist_ok=True)

    # Include exam_id in the filename
    csv_file = os.path.join(folder, f"suspicious_events_{student_id}_{exam_id}.csv")

    if not os.path.exists(csv_file):
        init_student_csv(student_id, exam_id)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(csv_file, mode="a", newline="") as f:
        csv.writer(f).writerow([timestamp, duration_sec, event_label])


# ================================
# LAZY MODEL LOADING
# ================================
_spk_model = None
_vad_model = None
_get_speech_timestamps = None
_osd_pipeline = None


def get_spk_model():
    global _spk_model
    if _spk_model is None:
        _spk_model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            run_opts={"device": "cpu"}
        )
    return _spk_model


def get_vad_model():
    global _vad_model, _get_speech_timestamps
    if _vad_model is None:
        _vad_model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True
        )
        # Handle both old API (5-tuple) and new API (object with attributes)
        if isinstance(utils, (list, tuple)):
            _get_speech_timestamps = utils[0]
        else:
            _get_speech_timestamps = utils.get_speech_timestamps
    return _vad_model, _get_speech_timestamps


def get_osd_pipeline():
    global _osd_pipeline
    if _osd_pipeline is None:
        # Patch torch.load for pyannote compatibility
        _original_torch_load = torch.load

        def patched_torch_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return _original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load

        from pyannote.audio import Pipeline
        HF_TOKEN = os.environ.get("HF_TOKEN", "HF_TOKEN_PLACEHOLDER")
        _osd_pipeline = Pipeline.from_pretrained(
            "pyannote/overlapped-speech-detection",
            token=HF_TOKEN
        )
    return _osd_pipeline


# ================================
# VAD
# ================================
def apply_vad(audio_tensor):
    vad_model, get_speech_timestamps = get_vad_model()

    MIN_SAMPLES = 512
    if audio_tensor.shape[-1] < MIN_SAMPLES:
        audio_tensor = torch.nn.functional.pad(
            audio_tensor, (0, MIN_SAMPLES - audio_tensor.shape[-1])
        )

    speech_timestamps = get_speech_timestamps(
        audio_tensor,
        vad_model,
        sampling_rate=SAMPLING_RATE,
        threshold=0.4
    )

    if len(speech_timestamps) == 0:
        return None

    segments = []
    for seg in speech_timestamps:
        # Old silero API: seg is dict {"start": x, "end": y}
        # New silero API: seg is object with .start / .end
        if isinstance(seg, dict):
            start, end = seg["start"], seg["end"]
        else:
            start, end = seg.start, seg.end
        segments.append(audio_tensor[start:end])

    if len(segments) == 0:
        return None

    speech = torch.cat(segments)

    if speech.shape[0] < SPEECH_MIN_LENGTH * SAMPLING_RATE:
        return None

    return speech


# ================================
# OVERLAP DETECTION
# ================================
# def detect_overlap(audio_tensor):
#     """Returns True if overlapping speech detected."""
#     try:
#         pipeline = get_osd_pipeline()
#         temp_file = "temp_overlap.wav"
#         torchaudio.save(temp_file, audio_tensor.unsqueeze(0), SAMPLING_RATE)
#         output = pipeline(temp_file)
#         for segment, _, label in output.itertracks(yield_label=True):
#             if label == "OVERLAP":
#                 return True
#     except Exception as e:
#         print(f"[OVERLAP] Error: {e}")
#     return False

# def detect_overlap(audio_tensor):
#     try:
#         pipeline = get_osd_pipeline()
#         temp_file = "temp_overlap.wav"
#         torchaudio.save(temp_file, audio_tensor.unsqueeze(0), SAMPLING_RATE)
#         output = pipeline(temp_file)
#
#         # ── print ALL segments to see what pyannote actually returns
#         print("[OVERLAP] all segments:")
#         for segment, _, label in output.itertracks(yield_label=True):
#             print(f"  segment={segment}, label={label}")
#
#         # check for overlap
#         for segment, _, label in output.itertracks(yield_label=True):
#             if label == "OVERLAP":
#                 return True
#
#     except Exception as e:
#         print(f"[OVERLAP] Error: {e}")
#
#     print("[OVERLAP] no overlap found")
#     return False


def detect_overlap(audio_tensor):
    try:
        frame_size = int(0.5 * SAMPLING_RATE)   # 500 ms
        hop_size = frame_size // 2

        if len(audio_tensor) < frame_size * 2:
            return False

        frames = audio_tensor.unfold(0, frame_size, hop_size)

        # Normalize frames
        frames = frames - frames.mean(dim=1, keepdim=True)
        frames = frames / (frames.std(dim=1, keepdim=True) + 1e-8)

        # --- 1. Frame-to-frame similarity ---
        similarities = []
        for i in range(len(frames) - 1):
            sim = torch.cosine_similarity(frames[i], frames[i+1], dim=0)
            similarities.append(sim.item())

        similarities = torch.tensor(similarities)

        mean_sim = similarities.mean().item()
        std_sim = similarities.std().item()

        # --- 2. Spectral entropy (important) ---
        fft = torch.fft.rfft(audio_tensor)
        power = torch.abs(fft) ** 2
        prob = power / (power.sum() + 1e-8)
        entropy = -(prob * torch.log(prob + 1e-8)).sum().item()

        # --- 3. Zero-crossing rate ---
        zcr = ((audio_tensor[:-1] * audio_tensor[1:]) < 0).float().mean().item()

        # ✅ FINAL DECISION
        is_overlap = (
                mean_sim < 0.65 and (std_sim > 0.03) and (std_sim < 0.09) and entropy > 7 and zcr > 0.1
        )

        print(f"[OVERLAP] sim={mean_sim:.2f}, std={std_sim:.2f}, ent={entropy:.2f}, zcr={zcr:.2f} → {'OVERLAP' if is_overlap else 'NO'}")

        return is_overlap

    except Exception as e:
        print(e)
        return False
# ================================
# SPEAKER EMBEDDING
# ================================
def get_speaker_embedding(audio_tensor):
    """
    Applies VAD, splits into chunks, encodes each chunk,
    returns mean normalized embedding or None if no speech.
    """
    speech = apply_vad(audio_tensor)
    if speech is None:
        return None

    spk_model = get_spk_model()
    student_embeddings = []
    chunk_size = SAMPLING_RATE * CHUNK_SECONDS
    chunks = speech.split(chunk_size)

    with torch.no_grad():
        for chunk in chunks:
            if len(chunk) > SAMPLING_RATE:
                emb = spk_model.encode_batch(chunk.unsqueeze(0))
                emb = emb.squeeze()
                emb = emb / torch.norm(emb)
                student_embeddings.append(emb)

    if not student_embeddings:
        return None

    mean_embedding = torch.mean(torch.stack(student_embeddings), dim=0)
    mean_embedding = mean_embedding / torch.norm(mean_embedding)
    return mean_embedding


# ================================
# FULL MONITORING ANALYSIS
# (called by Flask /analyze_audio route)
# ================================
# def analyze_audio_chunk(audio_tensor, mean_embedding, same_speaker_count):
#     """
#     Runs full analysis: VAD → overlap check → speaker check.
#
#     Returns dict:
#         status: "no_speech" | "overlap" | "same_speaker" | "different_speaker"
#         score: float (cosine similarity, if speaker check ran)
#         same_speaker_count: updated count
#         duration_sec: float
#     """
#     speech = apply_vad(audio_tensor)
#
#     if speech is None:
#         return {"status": "no_speech", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": 0}
#
#     if speech.shape[0] < SAMPLING_RATE:
#         return {"status": "no_speech", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": 0}
#
#     duration_sec = len(speech) / SAMPLING_RATE
#
#     # ── 1. Overlap check ─────────────────────────────────────────
#     if detect_overlap(speech):
#         log_suspicious_event(duration_sec, "OVERLAP")
#         return {"status": "overlap", "score": 0,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}
#
#     # ── 2. Speaker check ─────────────────────────────────────────
#     if mean_embedding is None:
#         return {"status": "no_enrollment", "score": 0,
#                 "same_speaker_count": same_speaker_count, "duration_sec": duration_sec}
#
#     spk_model = get_spk_model()
#     with torch.no_grad():
#         emb = spk_model.encode_batch(speech.unsqueeze(0))
#         emb = emb.squeeze()
#         emb = emb / torch.norm(emb)
#
#     mean_embedding = torch.tensor(mean_embedding) if not isinstance(
#         mean_embedding, torch.Tensor) else mean_embedding
#
#     similarity = torch.cosine_similarity(emb, mean_embedding, dim=0).item()
#
#     if similarity >= SIMILARITY_THRESHOLD:
#         same_speaker_count += 1
#         if same_speaker_count >= SAME_SPEAKER_LIMIT:
#             log_suspicious_event(duration_sec, "SAME_PERSON_TOO_MUCH")
#             same_speaker_count = 0
#             return {"status": "same_speaker_suspicious", "score": similarity,
#                     "same_speaker_count": same_speaker_count,
#                     "duration_sec": duration_sec}
#         return {"status": "same_speaker", "score": similarity,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}
#     else:
#         log_suspicious_event(duration_sec, "DIFFERENT_SPEAKER")
#         return {"status": "different_speaker", "score": similarity,
#                 "same_speaker_count": same_speaker_count,
#                 "duration_sec": duration_sec}


def analyze_audio_chunk(audio_tensor, mean_embedding, same_speaker_count, student_id, exam_id="unknown"):
    speech = apply_vad(audio_tensor)

    if speech is None or speech.shape[0] < SAMPLING_RATE:
        return {"status": "no_speech", "score": 0,
                "same_speaker_count": same_speaker_count,
                "duration_sec": 0}

    duration_sec = len(speech) / SAMPLING_RATE

    # ── 1. Overlap check first ─────────────────────────────────────
    if detect_overlap(speech):
        log_suspicious_event(student_id, exam_id, duration_sec, "OVERLAP")
        return {"status": "overlap", "score": 0,
                "same_speaker_count": same_speaker_count,
                "duration_sec": duration_sec}

    # ── 2. Speaker check ──────────────────────────────────────────
    if mean_embedding is None:
        return {"status": "no_enrollment", "score": 0,
                "same_speaker_count": same_speaker_count,
                "duration_sec": duration_sec}

    spk_model = get_spk_model()
    with torch.no_grad():
        emb = spk_model.encode_batch(speech.unsqueeze(0)).squeeze()
        emb = emb / torch.norm(emb)

    mean_embedding = torch.tensor(mean_embedding) if not isinstance(mean_embedding, torch.Tensor) else mean_embedding
    similarity = torch.cosine_similarity(emb, mean_embedding, dim=0).item()

    # ── 3. Same speaker logic with limit ─────────────────────────
    if similarity >= SIMILARITY_THRESHOLD:
        same_speaker_count += 1
        if same_speaker_count >= SAME_SPEAKER_LIMIT:
            log_suspicious_event(student_id, exam_id, duration_sec, "SAME_PERSON_TOO_MUCH")
            same_speaker_count = 0
            return {"status": "same_speaker_suspicious", "score": similarity,
                    "same_speaker_count": same_speaker_count,
                    "duration_sec": duration_sec}
        return {"status": "same_speaker", "score": similarity,
                "same_speaker_count": same_speaker_count,
                "duration_sec": duration_sec}

    # ── 4. Different speaker ──────────────────────────────────────
    log_suspicious_event(student_id, exam_id, duration_sec, "DIFFERENT_SPEAKER")
    return {"status": "different_speaker", "score": similarity,
            "same_speaker_count": same_speaker_count,
            "duration_sec": duration_sec}

