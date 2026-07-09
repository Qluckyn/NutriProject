from typing import Dict, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torchvision import transforms

import model_loader
from config import DEVICE, POSITIVE_CLASS
from classify_model.narrative_report import build_attention_text_from_face_normalized_scores
from classify_model.roi_attention import (
    ClassSpecificGradientRollout,
    DynamicROIAttentionAnalyzer,
    compute_face_normalized_roi_map_scores,
    draw_roi_visualization,
    draw_visualization,
)

ROI_NAMES: Tuple[str, ...] = ("temporal", "orbital", "malar", "jawline")
TARGET_CLASS_NOTE = "以下展示的是营养不良风险的关注依据，供参考"

_GEOMETRY_TRANSFORM = transforms.Compose(
    [
        transforms.Resize(224, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(224),
    ]
)
_TENSOR_TRANSFORM = transforms.Compose(
    [
        transforms.ToTensor(),
        transforms.Normalize(
            mean=(0.48145466, 0.4578275, 0.40821073),
            std=(0.26862954, 0.26130258, 0.27577711),
        ),
    ]
)

_explainer: Optional[ClassSpecificGradientRollout] = None
_explainer_model_id: Optional[int] = None
_roi_analyzer: Optional[DynamicROIAttentionAnalyzer] = None


def _preprocess_for_explain(image: Image.Image) -> tuple[torch.Tensor, np.ndarray]:
    """Create aligned model tensor and visualization image from one 224 crop."""

    aligned_pil = _GEOMETRY_TRANSFORM(image.convert("RGB"))
    image_np = np.asarray(aligned_pil, dtype=np.uint8)
    image_tensor = _TENSOR_TRANSFORM(aligned_pil).unsqueeze(0).to(DEVICE)
    return image_tensor, image_np


def _get_explainer() -> ClassSpecificGradientRollout:
    global _explainer, _explainer_model_id
    model = model_loader.ensure_model_loaded()
    if _explainer is None or _explainer_model_id != id(model):
        _explainer = ClassSpecificGradientRollout(model)
        _explainer_model_id = id(model)
    return _explainer


def _get_roi_analyzer() -> DynamicROIAttentionAnalyzer:
    global _roi_analyzer
    if _roi_analyzer is None:
        _roi_analyzer = DynamicROIAttentionAnalyzer(use_insightface_fallback=False)
    return _roi_analyzer


def _normalize_attention_map(attn_map: np.ndarray) -> np.ndarray:
    arr = np.asarray(attn_map, dtype=np.float32)
    return (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)


def explain_single_view(image: Image.Image, view_name: str) -> Dict[str, object]:
    """Generate ROI heatmap and attention text for one face view."""

    try:
        image_tensor, image_np = _preprocess_for_explain(image)
        explainer = _get_explainer()
        roi_analyzer = _get_roi_analyzer()

        explanation = explainer(image_tensor, target_class=POSITIVE_CLASS)
        masks = roi_analyzer.generate_roi_and_face_masks(image_np, view_name=view_name)
        if masks is None:
            return {
                "status": "failed",
                "heatmap_base64": None,
                "roi_overlay_base64": None,
                "attention_text": None,
                "reason": "人脸关键点或人脸区域检测失败",
            }
        roi_masks, face_mask = masks

        attn_map = explanation["attn_map"]
        roi_scores = compute_face_normalized_roi_map_scores(attn_map, roi_masks, face_mask)
        heatmap_base64 = draw_visualization(
            image_np,
            attn_map=_normalize_attention_map(attn_map),
            return_base64=True,
        )
        roi_overlay_base64 = draw_roi_visualization(
            image_np,
            roi_masks,
            return_base64=True,
        )
        attention_text = build_attention_text_from_face_normalized_scores(roi_scores)
        return {
            "status": "ok",
            "heatmap_base64": heatmap_base64,
            "roi_overlay_base64": roi_overlay_base64,
            "attention_text": attention_text,
            "reason": None,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "heatmap_base64": None,
            "roi_overlay_base64": None,
            "attention_text": None,
            "reason": f"可解释性结果生成失败：{exc}",
        }
