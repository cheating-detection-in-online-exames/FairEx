#
# import torch
# import sounddevice as sd
# import numpy as np
# import tkinter as tk
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# from speechbrain.inference import EncoderClassifier
# # ------------------------------------------------------------------- the overlap import
#
# import torchaudio
# import os
#
# # script for csv
# import csv
# from datetime import datetime
#
# CSV_FILE = "suspicious_events.csv"
#
# # -------------------------
# # 1️⃣ Initialize CSV (overwrite on each run)
# # -------------------------
# with open(CSV_FILE, mode="w", newline="") as f:
#     writer = csv.writer(f)
#     writer.writerow(["timestamp", "duration_sec", "event_label"])
#
# # -------------------------
# # 2️⃣ Logging function
# # -------------------------
# def log_suspicious_event(duration_sec, event_label):
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#
#     with open(CSV_FILE, mode="a", newline="") as f:
#         writer = csv.writer(f)
#         writer.writerow([timestamp, duration_sec, event_label])
#
# # ================================
# # CONFIG
# # ================================
# SAMPLING_RATE = 16000
# BLOCK_SIZE = 1024
# ENROLL_SECONDS = 8
# MONITOR_SECONDS = 5
# SPEECH_MIN_LENGTH = 1.0
# SIMILARITY_THRESHOLD = 0.39
# CHUNK_SECONDS = 2
#
#
# # ================================
# # LOAD SPEAKER MODEL (SpeechBrain ECAPA)
# # ================================
# spk_model = EncoderClassifier.from_hparams(
#     source="speechbrain/spkrec-ecapa-voxceleb",
#     run_opts={"device": "cpu"}
# )
#
# # ================================
# # LOAD SILERO VAD
# # ================================
# vad_model, utils = torch.hub.load(
#     repo_or_dir="snakers4/silero-vad",
#     model="silero_vad",
#     trust_repo=True
# )
#
# (get_speech_timestamps, _, _, _, _) = utils
#
# # ------------------------------------------------------------------- the overlap
# # ================================
# # LOAD OVERLAP DETECTION MODEL (Pyannote)
# # ================================
# import torch
#
# # Force PyTorch to allow full checkpoint loading (trusted HF model)
# _original_torch_load = torch.load
#
# def patched_torch_load(*args, **kwargs):
#     kwargs["weights_only"] = False
#     return _original_torch_load(*args, **kwargs)
#
# torch.load = patched_torch_load
#
# from pyannote.audio import Pipeline
#
# HF_TOKEN = os.environ.get("HF_TOKEN")
#
# osd_pipeline = Pipeline.from_pretrained(
#     "pyannote/overlapped-speech-detection",
#     use_auth_token=HF_TOKEN
# )
#
#
# print("==================================>" ,torchaudio.list_audio_backends())
#
# # ================================
# # GLOBALS
# # ================================
# student_embeddings = []
# mean_embedding = None
# recording_audio = []
# monitor_audio = []
# stream = None
# remaining_time = 0
# monitoring_active = False
# suspicious_count = 0
# same_speaker_count = 0
# SAME_SPEAKER_LIMIT = 3
#
# # ================================
# # GUI
# # ================================
# root = tk.Tk()
# root.title("Voice Exam Monitoring System")
# root.geometry("700x600")
#
# title = tk.Label(root, text="AI Voice Monitoring System", font=("Arial", 18))
# title.pack(pady=10)
#
# countdown_label = tk.Label(root, text="Ready", font=("Arial", 22))
# countdown_label.pack()
#
# status_label = tk.Label(root, text="System Ready", font=("Arial", 12))
# status_label.pack()
#
# score_label = tk.Label(root, text="Similarity: --", font=("Arial", 14))
# score_label.pack(pady=5)
#
# suspicious_label = tk.Label(root, text="Suspicious Count: 0", font=("Arial", 14))
# suspicious_label.pack(pady=5)
#
# # ================================
# # Waveform
# # ================================
# fig, ax = plt.subplots(figsize=(6, 2))
# x = np.arange(0, BLOCK_SIZE)
# y = np.zeros(BLOCK_SIZE)
# waveform_line, = ax.plot(x, y)
#
# ax.set_ylim(-1, 1)
# ax.set_xlim(0, BLOCK_SIZE)
# ax.set_title("Live Waveform")
#
# canvas = FigureCanvasTkAgg(fig, master=root)
# canvas.get_tk_widget().pack(pady=20)
#
# # ================================
# # AUDIO CALLBACK
# # ================================
# def audio_callback(indata, frames, time, status):
#     global recording_audio, monitor_audio
#
#     waveform_line.set_ydata(indata[:, 0])
#     canvas.draw_idle()
#
#     if remaining_time > 0:
#         recording_audio.append(indata.copy())
#
#     if monitoring_active:
#         monitor_audio.append(indata.copy())
#
# # ================================
# # NON BLOCKING NOTIFICATION
# # ================================
# def show_notification(text, color):
#     notif = tk.Label(root, text=text, bg=color, fg="white", font=("Arial", 14))
#     notif.place(relx=0.5, rely=0.9, anchor="center")
#     root.after(2000, notif.destroy)
#
# # ================================
# # VAD
# # ================================
# def apply_vad(audio_tensor):
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
# # ================================
# # ENROLLMENT
# # ================================
# def start_enrollment():
#     global recording_audio, remaining_time, stream
#     recording_audio = []
#     remaining_time = ENROLL_SECONDS
#     status_label.config(text="Enrollment Recording...")
#
#     stream = sd.InputStream(
#         samplerate=SAMPLING_RATE,
#         blocksize=BLOCK_SIZE,
#         channels=1,
#         callback=audio_callback
#     )
#
#     stream.start()
#     update_countdown_enroll()
#
# def update_countdown_enroll():
#     global remaining_time
#
#     if remaining_time > 0:
#         countdown_label.config(text=str(remaining_time))
#         remaining_time -= 1
#         root.after(1000, update_countdown_enroll)
#     else:
#         stream.stop()
#         stream.close()
#         finish_enrollment()
#
# def finish_enrollment():
#     global student_embeddings, mean_embedding
#
#     audio = np.concatenate(recording_audio, axis=0)
#     # audio_tensor = torch.from_numpy(audio.flatten()).float() ----------the laud sound
#     audio_tensor = torch.from_numpy(audio.flatten()).float()
#     audio_tensor = audio_tensor / (audio_tensor.abs().max() + 1e-6)
#
#     speech = apply_vad(audio_tensor)
#
#     if speech is None:
#         show_notification("No speech detected!", "red")
#         return
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
#                 emb = emb / torch.norm(emb)
#                 student_embeddings.append(emb)
#
#     mean_embedding = torch.mean(torch.stack(student_embeddings), dim=0)
#     mean_embedding = mean_embedding / torch.norm(mean_embedding)
#
#     status_label.config(text="Enrollment Complete ✅")
#     countdown_label.config(text="Done")
#
# # ================================
# # SPEAKER CHECK
# # ================================
# def is_same_speaker(emb):
#     global mean_embedding
#
#     similarity = torch.cosine_similarity(emb, mean_embedding, dim=0).item()
#     score_label.config(text=f"Similarity: {similarity:.2f}")
#
#     return similarity >= SIMILARITY_THRESHOLD
#
# # ================================
# # MONITORING
# # ================================
# def start_monitoring():
#     global monitor_audio, monitoring_active, stream
#
#     if mean_embedding is None:
#         show_notification("Enroll student first!", "red")
#         return
#
#     monitoring_active = True
#     monitor_audio = []
#     status_label.config(text="Monitoring Started...")
#
#     stream = sd.InputStream(
#         samplerate=SAMPLING_RATE,
#         blocksize=BLOCK_SIZE,
#         channels=1,
#         callback=audio_callback
#     )
#
#     stream.start()
#     root.after(MONITOR_SECONDS * 1000, process_monitoring)
#
# # ------------------------------------------------------------------- the overlap
#
#
# # ================================
# # OVERLAP DETECTION
# # ================================
# def detect_overlap(audio_tensor):
#     """
#     Takes torch tensor (speech only)
#     Returns True if overlapping detected
#     """
#
#     temp_file = "temp_overlap.wav"
#
#     # Save tensor to temporary wav file
#     torchaudio.save(temp_file, audio_tensor.unsqueeze(0), SAMPLING_RATE)
#
#     output = osd_pipeline(temp_file)
#
#     # Check if any overlap segments exist
#     for segment, _, label in output.itertracks(yield_label=True):
#         if label == "OVERLAP":
#             return True
#
#     return False
#
#
#
# def process_monitoring():
#     global monitor_audio, suspicious_count, same_speaker_count
#
#     if not monitoring_active:
#         return
#
#     if len(monitor_audio) == 0:
#         root.after(MONITOR_SECONDS * 1000, process_monitoring)
#         return
#
#     audio = np.concatenate(monitor_audio, axis=0)
#     monitor_audio = []
#
#     audio_tensor = torch.from_numpy(audio.flatten()).float()
#     audio_tensor = audio_tensor / (audio_tensor.abs().max() + 1e-6)
#
#     speech = apply_vad(audio_tensor)
#
#     if speech is None:
#         status_label.config(text="No speech detected")
#         root.after(MONITOR_SECONDS * 1000, process_monitoring)
#         return
#
#     # Safety length check
#     if speech.shape[0] < SAMPLING_RATE:
#         root.after(MONITOR_SECONDS * 1000, process_monitoring)
#         return
#
#     # ================================
#     # 1️⃣ OVERLAP CHECK
#     # ================================
#     if detect_overlap(speech):
#         suspicious_count += 1
#         # same_speaker_count = 0
#
#         suspicious_label.config(text=f"Suspicious Count: {suspicious_count}")
#         status_label.config(text="Overlapping speech detected 🚨")
#         show_notification("⚠ Two people speaking!", "purple")
#
#         # Log to CSV
#         log_suspicious_event(
#             duration_sec=len(speech ) /SAMPLING_RATE,
#             event_label="OVERLAP"
#         )
#         root.after(MONITOR_SECONDS * 1000, process_monitoring)
#         return
#
#     # ================================
#     # 2️⃣ SPEAKER CHECK
#     # ================================
#     with torch.no_grad():
#         emb = spk_model.encode_batch(speech.unsqueeze(0))
#         emb = emb.squeeze()
#         emb = emb / torch.norm(emb)
#
#     if is_same_speaker(emb):
#
#         same_speaker_count += 1
#         status_label.config(
#             text=f"Same student speaking ({same_speaker_count}/{SAME_SPEAKER_LIMIT})"
#         )
#
#         if same_speaker_count >= SAME_SPEAKER_LIMIT:
#             suspicious_count += 1
#             suspicious_label.config(text=f"Suspicious Count: {suspicious_count}")
#
#             show_notification(
#                 "⚠ Student spoke too many times! Suspicious behavior!",
#                 "orange"
#             )
#             log_suspicious_event(
#
#                 duration_sec=len(speech ) /SAMPLING_RATE,
#                 event_label="SAME_PERSION"
#             )
#             same_speaker_count = 0
#         root.after(MONITOR_SECONDS * 1000, process_monitoring)
#
#     else:
#         suspicious_count += 1
#         # same_speaker_count = 0
#
#         suspicious_label.config(text=f"Suspicious Count: {suspicious_count}")
#         status_label.config(text="Different speaker detected 🚨")
#         show_notification("Suspicious voice detected!", "red")
#
#         log_suspicious_event(
#             duration_sec=len(speech ) /SAMPLING_RATE,
#             event_label="DIFFERENT_SPEAKER"
#         )
#     root.after(MONITOR_SECONDS * 1000, process_monitoring)
#
# def stop_monitoring():
#     global monitoring_active
#
#     monitoring_active = False
#     if stream:
#         stream.stop()
#         stream.close()
#
#     status_label.config(text="Monitoring Stopped")
#
# # ================================
# # BUTTONS
# # ================================
# enroll_btn = tk.Button(root, text="🎤 Enroll Student", command=start_enrollment, width=20)
# enroll_btn.pack(pady=5)
#
# start_btn = tk.Button(root, text="▶ Start Monitoring", command=start_monitoring, width=20)
# start_btn.pack(pady=5)
#
# stop_btn = tk.Button(root, text="⏹ Stop Monitoring", command=stop_monitoring, width=20)
# stop_btn.pack(pady=5)
#
# root.mainloop()
#