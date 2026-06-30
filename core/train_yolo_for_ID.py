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

def _predict(img):
    results = model.predict(img, verbose=False)
    if not results:
        return np.array([]), np.array([]), np.array([])
    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return np.array([]), np.array([]), np.array([])
    return (result.boxes.xyxy.cpu().numpy(),
            result.boxes.cls.cpu().numpy(),
            result.boxes.conf.cpu().numpy())

def detect_id_objects(image_path):
    img = cv2.imread(image_path)
    boxes, classes, scores = _predict(img)

    if is_egyptian_id(classes):
        return boxes, classes, scores

    # Try 180°, 90°, 270° until a valid ID is found
    for angle in [180, 90, 270]:
        rotated = _rotate_image(img, angle)
        boxes, classes, scores = _predict(rotated)
        if is_egyptian_id(classes):
            cv2.imwrite(image_path, rotated)  # fix orientation in-place
            return boxes, classes, scores

    return np.array([]), np.array([]), np.array([])

def is_egyptian_id(classes):
    found = set(classes)
    if 0 in found and (1 in found or 2 in found) and 3 in found:
        return True
    return False

def _rotate_image(img, angle):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h))

def _find_face(img):
    results = model.predict(img, verbose=False)
    if not results:
        return None, None
    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        return None, None
    classes = result.boxes.cls.cpu().numpy()
    boxes = result.boxes.xyxy.cpu().numpy()
    face_indices = [i for i, cls in enumerate(classes) if cls == 0]
    if not face_indices:
        return None, None
    return boxes[face_indices[0]], classes

def crop_face(image_path, boxes, classes, save_dir="cropped_faces"):
    os.makedirs(save_dir, exist_ok=True)
    img = cv2.imread(image_path)
    save_path = os.path.join(save_dir, os.path.basename(image_path))

    # Try original orientation first
    face_indices = [i for i, cls in enumerate(classes) if cls == 0]
    if face_indices:
        x1, y1, x2, y2 = map(int, boxes[face_indices[0]])
        cv2.imwrite(save_path, img[y1:y2, x1:x2])
        return save_path

    # Rotate by 45° increments until a face is found
    for angle in range(45, 360, 45):
        rotated = _rotate_image(img, angle)
        face_box, _ = _find_face(rotated)
        if face_box is not None:
            x1, y1, x2, y2 = map(int, face_box)
            cv2.imwrite(save_path, rotated[y1:y2, x1:x2])
            return save_path

    return None
