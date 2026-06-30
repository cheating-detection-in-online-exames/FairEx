# from ultralytics import YOLO
# import cv2
# import os
# import matplotlib.pyplot as plt
# import numpy as np
#
# # Load the model from the path you downloaded
# model = YOLO(r"trained_models/best.pt")
#
# # # Test on a single image
# # image_path = r"C:\Users\Hager ElSherif\OneDrive\الصور\Camera Roll\132778.jpg"
# # results = model.predict(image_path, show=True)  # show=True will display the image
# # # Convert first result to OpenCV image with boxes drawn
# # img_with_boxes = results[0].plot()  # This returns an image (numpy array) with boxes drawn
# #
# # # Show with matplotlib
# # plt.figure(figsize=(10,10))
# # plt.imshow(cv2.cvtColor(img_with_boxes, cv2.COLOR_BGR2RGB))
# # plt.axis('off')
# # plt.show()
#
# def detect_id_objects(image_path):
#     results = model.predict(image_path, verbose=False)
#     if not results:
#         return np.array([]), np.array([]), np.array([])  # return empty arrays
#
#     result = results[0]
#     if result.boxes is None or len(result.boxes) == 0:
#         return np.array([]), np.array([]), np.array([])  # no detections
#
#     boxes = result.boxes.xyxy.cpu().numpy()  # [x1, y1, x2, y2]
#     classes = result.boxes.cls.cpu().numpy()  # class IDs
#     scores = result.boxes.conf.cpu().numpy()  # confidence
#     return boxes, classes, scores
#
# def is_egyptian_id(classes):
#     required_classes = [0, 1, 2, 3]  # Face, Name1, Name2, Num1
#     found = set(classes)
#     # Allow flexibility: at least face + one name + num
#     if 0 in found and (1 in found or 2 in found) and 3 in found:
#         return True
#     return False
#
#
# def crop_face(image_path, boxes, classes, save_dir="cropped_faces"):
#     os.makedirs(save_dir, exist_ok=True)
#     img = cv2.imread(image_path)
#
#     # Find the Face box
#     face_indices = [i for i, cls in enumerate(classes) if cls == 0]
#     if not face_indices:
#         return None
#     face_box = boxes[face_indices[0]]  # Use first face detected
#     x1, y1, x2, y2 = map(int, face_box)
#
#     face_crop = img[y1:y2, x1:x2]
#
#     # Save cropped face
#     base_name = os.path.basename(image_path)
#     save_path = os.path.join(save_dir, f"face_{base_name}")
#     cv2.imwrite(save_path, face_crop)
#
#     return save_path
#
# image_path = r"WhatsApp Image 2026-02-21 at 4.45.43 PM.jpeg"
#
# boxes, classes, scores = detect_id_objects(image_path)
#
# if boxes is not None:
#     if is_egyptian_id(classes):
#         print("✅ This image is likely an Egyptian ID.")
#         face_path = crop_face(image_path, boxes, classes)
#         print(f"Face cropped and saved at: {face_path}")
#     else:
#         print("❌ Not enough ID elements detected. Possibly not an Egyptian ID.")
# else:
#     print("❌ No objects detected. Possibly not an Egyptian ID.")
#
#
#


# yolo_id_utils.py

from ultralytics import YOLO
import cv2
import os
import numpy as np

# Load the model once
MODEL_PATH = r"trained_models/best.pt"
model = YOLO(MODEL_PATH)

def detect_id_objects(image_path):
    """
    Detect objects in an Egyptian ID image using YOLO.
    Returns: boxes, classes, scores (all numpy arrays)
    """
    results = model.predict(image_path, verbose=False)
    if not results:
        return np.array([]), np.array([]), np.array([])

    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return np.array([]), np.array([]), np.array([])

    boxes = result.boxes.xyxy.cpu().numpy()  # [x1, y1, x2, y2]
    classes = result.boxes.cls.cpu().numpy()  # class IDs
    scores = result.boxes.conf.cpu().numpy()  # confidence
    return boxes, classes, scores

def is_egyptian_id(classes):
    """
    Check if the detected classes satisfy Egyptian ID requirements.
    Must have at least: Face, one Name, Num1
    """
    found = set(classes)
    if 0 in found and (1 in found or 2 in found) and 3 in found:
        return True
    return False

def crop_face(image_path, boxes, classes, save_dir="cropped_faces"):
    """
    Crop the face from the detected boxes and save it.
    Returns the saved path or None if no face detected.
    """
    os.makedirs(save_dir, exist_ok=True)
    img = cv2.imread(image_path)

    # Find the Face box
    face_indices = [i for i, cls in enumerate(classes) if cls == 0]
    if not face_indices:
        return None
    face_box = boxes[face_indices[0]]  # Use first face detected
    x1, y1, x2, y2 = map(int, face_box)

    face_crop = img[y1:y2, x1:x2]

    # Save cropped face
    base_name = os.path.basename(image_path)
    save_path = os.path.join(save_dir, f"{base_name}")
    cv2.imwrite(save_path, face_crop)

    return save_path
