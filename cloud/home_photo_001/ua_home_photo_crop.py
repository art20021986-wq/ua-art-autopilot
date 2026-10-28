"""Home page photo: find the car and frame it (HOME-PHOTO-001).

One job: photo bytes in, framed JPEG bytes out. The car is found by the
YOLOX-S detector of the OpenCV Model Zoo (Apache-2.0, COCO classes) run by
the OpenCV already installed on the server; the frame is a fixed 3:2 crop with
the car in the centre and a small margin around it. Nothing is written here.
"""
import io

import cv2
import numpy as np
from PIL import Image, ImageOps

MODEL = '/home/Carix/ua_home_photo/object_detection_yolox_2022nov.onnx'
MARGIN = 0.04          # free space left and right of the car, share of its width
MAX_WIDTH = 1800       # output is 1800×1200 or smaller, always exactly 3:2
MIN_CAR_WIDTH = 800    # a smaller car gives a blurry first screen
VEHICLES = (2, 5, 7)   # COCO: car, bus, truck (SUVs and pickups are often «truck»)
SCORE = 0.35
NMS_IOU = 0.5
SIZE = 640
STRIDES = (8, 16, 32)


class PhotoError(ValueError):
    """Reason the photo cannot be used; the code is shown to the owner by the bot."""


def _grid():
    cells = [(np.stack(np.meshgrid(np.arange(SIZE // s), np.arange(SIZE // s)), 2).reshape(-1, 2), s) for s in STRIDES]
    return np.concatenate([g for g, _ in cells]), np.concatenate([np.full((len(g), 1), s) for g, s in cells])


def detect_cars(rgb):
    """Vehicle boxes (x1, y1, x2, y2, score) in image pixels, largest first (YOLOX decoding as in the Model Zoo)."""
    h, w = rgb.shape[:2]
    scale = min(SIZE / h, SIZE / w)
    nh, nw = int(h * scale), int(w * scale)
    canvas = np.full((SIZE, SIZE, 3), 114.0, dtype=np.float32)
    canvas[:nh, :nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
    net = cv2.dnn.readNet(MODEL)  # loaded per photo: the bot does not keep ~100 MB for a rare action
    net.setInput(np.transpose(canvas, (2, 0, 1))[np.newaxis])
    dets = net.forward(net.getUnconnectedOutLayersNames())[0][0]
    grid, strides = _grid()
    centre = (dets[:, :2] + grid) * strides
    size = np.exp(dets[:, 2:4]) * strides
    scores = (dets[:, 4:5] * dets[:, 5:])[:, VEHICLES].max(axis=1)
    xywh = np.column_stack((centre - size / 2, size)) / scale
    keep = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), SCORE, NMS_IOU), dtype=int).ravel()
    found = []
    for i in keep:
        x, y, bw, bh = xywh[i]
        found.append((max(x, 0), max(y, 0), min(x + bw, w), min(y + bh, h), float(scores[i])))
    return sorted(found, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)


def frame(box, width, height):
    """Exact 3:2 crop (left, top, right, bottom): the car in the centre with MARGIN around it;
    a photo framed tighter than that gives the largest 3:2 crop around the car."""
    x1, y1, x2, y2 = box[:4]
    w = max((x2 - x1) * (1 + 2 * MARGIN), (y2 - y1) * (1 + 2 * MARGIN) * 3 / 2)
    h = int(min(w * 2 / 3, width * 2 / 3, height)) // 2 * 2
    w = h * 3 // 2
    left = round(min(max((x1 + x2 - w) / 2, 0), width - w))
    top = round(min(max((y1 + y2 - h) / 2, 0), height - h))
    return left, top, left + w, top + h


def make_home_photo(data):
    """Framed JPEG for the home first screen. Raises PhotoError."""
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert('RGB')
    except Exception:
        raise PhotoError('NOT_A_PHOTO') from None
    cars = detect_cars(np.asarray(image))
    if not cars:
        raise PhotoError('NO_CAR')
    if cars[0][2] - cars[0][0] < MIN_CAR_WIDTH:
        raise PhotoError('TOO_SMALL')
    image = image.crop(frame(cars[0], *image.size))
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, MAX_WIDTH * 2 // 3), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=86, optimize=True, progressive=True)
    return out.getvalue()
