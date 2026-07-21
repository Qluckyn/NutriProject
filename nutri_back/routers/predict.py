from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

import model_loader
from config import CHECKPOINT_PATH, CLASS_NAMES, DEVICE, POSITIVE_CLASS, SUPPORTED_EXTENSIONS
from model_loader import (
    aggregate_scores,
    build_message,
    predict_one_view,
    read_image,
    round4,
)
from services.draft_service import draft_500, draft_image_path, read_draft_file
from services import scale_document_service

# 面部图像推理和服务状态接口路由。
router = APIRouter()


@router.get("/health")
def health() -> Dict[str, object]:
    return {"status": "ok", "model_loaded": model_loader.model is not None, "device": DEVICE}


@router.get("/info")
def info() -> Dict[str, object]:
    return {
        "model_name": "NutriCLIP",
        "dataset": "my_dataset",
        "clip_version": "ViT-B/16",
        "checkpoint_path": CHECKPOINT_PATH,
        "device": DEVICE,
        "classes": CLASS_NAMES,
        "positive_class": POSITIVE_CLASS,
        "supported_image_formats": sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS),
        "aggregation": "多视角营养不良概率取平均，阈值0.5判定为营养不良",
    }


@router.post("/predict")
async def predict(
    front: Optional[UploadFile] = File(None),
    left: Optional[UploadFile] = File(None),
    right: Optional[UploadFile] = File(None),
) -> Dict[str, object]:
    uploads = {"front": front, "left": left, "right": right}
    available_uploads = {name: file for name, file in uploads.items() if file is not None}

    if not available_uploads:
        raise HTTPException(status_code=400, detail="请至少上传一张面部图片。")

    per_view_scores: Dict[str, Dict[str, float]] = {}
    views_used: List[str] = []

    for view_name, upload in available_uploads.items():
        image = await read_image(upload, view_name)
        per_view_scores[view_name] = predict_one_view(image)
        views_used.append(view_name)

    prediction, mal_prob, normal_prob = aggregate_scores(per_view_scores)
    confidence = max(mal_prob, normal_prob)

    return {
        "prediction": prediction,
        "malnourished_probability": round4(mal_prob),
        "normal_probability": round4(normal_prob),
        "confidence": round4(confidence),
        "sga_normalized_score": round4(mal_prob * 7),
        "n_views_used": len(views_used),
        "views_used": views_used,
        "per_view_scores": per_view_scores,
        "message": build_message(prediction, mal_prob, views_used),
    }


@router.post("/predict/draft")
def predict_from_draft_images() -> Dict[str, object]:
    """直接使用已保存的草稿图片进行面部筛查，避免前端在预测时二次上传图片。"""
    try:
        draft = read_draft_file()
        images = draft.get("images") or {}
        views_used: List[str] = []
        per_view_scores: Dict[str, Dict[str, float]] = {}

        for view_name in ("front", "left", "right"):
            image_info = images.get(view_name)
            image_path = draft_image_path(view_name)
            if not image_info or not image_info.get("saved") or not image_path.exists():
                continue
            image = Image.open(image_path).convert("RGB")
            per_view_scores[view_name] = predict_one_view(image)
            views_used.append(view_name)

        if not views_used:
            raise HTTPException(status_code=400, detail="请至少先上传并保存一张面部图片。")

        prediction, mal_prob, normal_prob = aggregate_scores(per_view_scores)
        confidence = max(mal_prob, normal_prob)
        result = {
            "prediction": prediction,
            "malnourished_probability": round4(mal_prob),
            "normal_probability": round4(normal_prob),
            "confidence": round4(confidence),
            "sga_normalized_score": round4(mal_prob * 7),
            "n_views_used": len(views_used),
            "views_used": views_used,
            "per_view_scores": per_view_scores,
            "message": build_message(prediction, mal_prob, views_used),
        }
        result["document_output"] = scale_document_service.generate_sga_document(draft, result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("草稿图片筛查失败", exc)
