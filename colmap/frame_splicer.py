import cv2
import os
import sys
from datetime import datetime

# -------- SETTINGS --------
IMAGES_PER_SECOND = 5
# --------------------------

def extract_frames(video_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Could not open video: {video_path}")
        return

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    every_n = max(1, round(video_fps / IMAGES_PER_SECOND))
    print(f"Video FPS: {video_fps:.2f} -> extracting every {every_n} frames "
          f"(~{video_fps / every_n:.2f} images/sec)")

    frame_id = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_id % every_n == 0:
            filename = os.path.join(output_folder, f"img_{saved_count:05d}.jpg")
            cv2.imwrite(filename, frame)
            saved_count += 1

        frame_id += 1

    cap.release()
    print(f"Extracted {saved_count} images to '{output_folder}'")

def main():
    if len(sys.argv) < 2:
        print("Usage: python frame_splicer.py <video_file> [output_folder]")
        sys.exit(1)

    video_file = sys.argv[1]
    if not os.path.isfile(video_file):
        print(f"File not found: {video_file}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        image_folder = sys.argv[2]
    else:
        base = os.path.splitext(os.path.basename(video_file))[0]
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        image_folder = f"frames_{base}_{stamp}"

    extract_frames(video_file, image_folder)

if __name__ == "__main__":
    main()
