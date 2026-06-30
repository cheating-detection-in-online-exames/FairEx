import base64
import numpy as np
import cv2
from insightface.app import FaceAnalysis

arcface_model = FaceAnalysis()
arcface_model.prepare(ctx_id=0)

print("InsightFace loaded successfully")

# # Load ArcFace model once
# model = insightface.app.FaceAnalysis(name='buffalo_l')
# model.prepare(ctx_id=0)  # 0 = CPU, -1 = auto, 1 = GPU

def verify_arcface(img1_path, img2_path, threshold=0.32):
    # Read images 2d not path
    img1 = cv2.imread(img1_path)
    print(img1_path)
    img2 = cv2.imread(img2_path)
    print(img2_path)
    if img1 is None or img2 is None:
        return False  # File not found or cannot read

    # Get face embeddings
    face1 = arcface_model.get(img1)
    face2 = arcface_model.get(img2)

    if len(face1) == 0 or len(face2) == 0:
        return False  # No face detected

    emb1 = face1[0].embedding
    emb2 = face2[0].embedding

    # Cosine similarity
    score = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

    return score > threshold

def verify_arcface_live(saved_path, live_img_bytes, threshold=0.32):
    """Verifies a saved image against a live frame from memory (bytes)"""
    # 1. Read the saved ID face from the disk
    saved_img = cv2.imread(saved_path)
    if saved_img is None:
        return False

    # 2. Decode the live webcam frame directly from memory (no saving to disk)
    npimg = np.frombuffer(live_img_bytes, np.uint8)
    live_img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if live_img is None:
        return False

    # 3. Get face embeddings
    face1 = arcface_model.get(saved_img)
    face2 = arcface_model.get(live_img)

    if len(face1) == 0 or len(face2) == 0:
        return False  # No face detected in one of the images

    emb1 = face1[0].embedding
    emb2 = face2[0].embedding

    # 4. Calculate similarity
    score = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))

    return bool(score > threshold)



