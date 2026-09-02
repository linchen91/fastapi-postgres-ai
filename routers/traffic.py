import base64
import cv2
import numpy as np
import requests
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

@lru_cache(maxsize=1)
def get_yolo(model_path: str = "yolov8n.pt"):
    from ultralytics import YOLO
    return YOLO(model_path)  # Load the YOLOv8 model

router = APIRouter()

DEFAULT_VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}

class DetectVehiclesRequest(BaseModel):
    url: HttpUrl
    conf: Optional[float] = 0.2
    vehicle_classes: Optional[list[str]] = None

class DetectVehiclesResponse(BaseModel):
    vehicles: int
    by_class: dict[str, int]
    image_base64: str

UA = {"User-Agent": "Mozilla/5.0"}

def fetch_image_simple(url: str, timeout: int = 10) -> np.ndarray:
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()  # Raise an error for bad responses
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    ok, frame = cap.read()
    cap.release()
    if ok:
        return frame
    else:
        raise HTTPException(status_code=400, detail="Unable to fetch image from the provided URL.") 

def bgr_to_dataurl_jpeg(img: np.ndarray, quality: int = 90) -> str:
    ok, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode image to JPEG.")
    return "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")

@router.post("/cars", response_model=DetectVehiclesResponse)
def detect_vehicles(request: DetectVehiclesRequest):
    url = str(request.url)
    img = fetch_image_simple(url)
    model = get_yolo()
    allow = set(request.vehicle_classes) if request.vehicle_classes else DEFAULT_VEHICLE_CLASSES
    results = model(img, conf=request.conf, verbose=False)[0]

    by_class = {name: 0 for name in allow}
    total = 0

    for cls_id in results.boxes.cls:
        cls_name = model.names[int(cls_id)]
        if cls_name in allow:
            total += 1
            by_class[cls_name] += 1

    annotated_img = results.plot()
    image_base64 = bgr_to_dataurl_jpeg(annotated_img)

    return DetectVehiclesResponse(
        vehicles=total,
        by_class=by_class,
        image_base64=image_base64
    )