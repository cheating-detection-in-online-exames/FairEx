
# # ---------------------------
# # Paths - adjust if needed
# # ---------------------------
# # LFW_PATH = r"H:\Graduation Project\Authentication\electronics-website\lfw"  # path to extracted lfw folder
# # PAIRS_FILE = os.path.join(LFW_PATH, "pairs.txt")
# LFW_PATH = r"H:/Graduation Preject/archive"
# PAIRS_FILE = os.path.join(LFW_PATH, "pairs.txt")
# # ---------------------------
# # Load ArcFace model
# # ---------------------------
# model = insightface.app.FaceAnalysis(name='buffalo_l')
# model.prepare(ctx_id=0)  # CPU: 0, GPU: 1

# # ---------------------------
# # Load pairs
# # ---------------------------
# pairs = []
# with open(PAIRS_FILE, 'r') as f:
#     lines = f.readlines()[1:]  # skip header
#     for line in lines:
#         parts = line.strip().split()
#         if len(parts) == 3:  # same person
#             person, idx1, idx2 = parts
#             idx1 = int(idx1)
#             idx2 = int(idx2)
#             img1 = os.path.join(LFW_PATH,"lfw-funneled", "lfw_funneled", person, f"{person}_{int(idx1):04d}.jpg")
#             img2 = os.path.join(LFW_PATH,"lfw-funneled", "lfw_funneled", person, f"{person}_{int(idx2):04d}.jpg")
#             pairs.append((img1, img2, True))
#         elif len(parts) == 4:  # different people
#             person1, idx1, person2, idx2 = parts
#             idx1 = int(idx1)
#             idx2 = int(idx2)
#             img1 = os.path.join(LFW_PATH, person1, f"{person1}_{idx1:04d}.jpg")
#             img2 = os.path.join(LFW_PATH, person2, f"{person2}_{idx2:04d}.jpg")
#             pairs.append((img1, img2, False))

# # ---------------------------
# # Run verification
# # ---------------------------
# total = 0
# correct = 0
# skipped = 0

# for img1, img2, label in pairs:
#     result = verify_arcface(img1, img2)
#     if result is None:
#         skipped += 1
#         continue
#     if result == label:
#         correct += 1
#     total += 1

# accuracy = correct / total * 100
# print(f"Total pairs tested: {total}")
# print(f"Skipped pairs (no face / missing): {skipped}")
# print(f"Correct predictions: {correct}")
# print(f"Accuracy: {accuracy:.2f}%")

#----------------------------------->>>>>>>>>>>>>>





# def evaluate_pairs(pair_file, images_path):
#     total = 0
#     correct = 0
#     skipped = 0

#     with open(pair_file, 'r') as f:
#         lines = f.readlines()[1:]  # skip header

#     for line in lines:
#         parts = line.strip().split()
#         if len(parts) == 3:
#             name, idx1, idx2 = parts
#             img1 = os.path.join(images_path,"lfw-funneled", "lfw_funneled", name, f"{name}_{int(idx1):04d}.jpg")
#             img2 = os.path.join(images_path,"lfw-funneled", "lfw_funneled", name, f"{name}_{int(idx2):04d}.jpg")
#             label = 1
#         elif len(parts) == 4:
#             name1, idx1, name2, idx2 = parts
#             img1 = os.path.join(images_path, "lfw-funneled", "lfw_funneled", name1, f"{name1}_{int(idx1):04d}.jpg")
#             img2 = os.path.join(images_path, "lfw-funneled", "lfw_funneled", name2, f"{name2}_{int(idx2):04d}.jpg")


#             label = 0
#         else:
#             continue

#         # Skip if files do not exist
#         if not os.path.exists(img1) or not os.path.exists(img2):
#             skipped += 1
#             continue

#         result = DeepFace.verify(img1, img2, enforce_detection=False)
#         predicted = 1 if result['verified'] else 0

#         if predicted == label:
#             correct += 1
#         total += 1

#     accuracy = correct / total if total > 0 else 0
#     print(f"DeepFace Accuracy on LFW test pairs: {accuracy*100:.2f}%")
#     print(f"Skipped {skipped} pairs because images were missing.")
#     return accuracy
