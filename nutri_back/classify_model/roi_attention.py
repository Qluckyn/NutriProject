"""ROI attention utilities for NutriCLIP inference.

This module is a compact runtime version of ``classify/roi_attention_analysis.py``.
It keeps only the positive class gradient rollout, dynamic ROI mask generation,
ROI enrichment scoring, and a single heatmap overlay visualization.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from PIL import Image

try:
    from config import CLASS_NAMES, DEVICE, POSITIVE_CLASS
except ImportError:  # pragma: no cover - package import fallback
    from nutri_back.config import CLASS_NAMES, DEVICE, POSITIVE_CLASS

try:
    from .passing.qc_filter import (
        ClinicalFeatureExtractor,
        FACE_OVAL,
        INSIGHTFACE_DET_SIZE,
        LEFT_JAW_LINE,
        LEFT_MALAR,
        LEFT_ORBITAL,
        LEFT_TEMPORAL,
        MODEL_PATH,
        RIGHT_JAW_LINE,
        RIGHT_MALAR,
        RIGHT_ORBITAL,
        RIGHT_TEMPORAL,
    )
except ImportError:  # pragma: no cover - direct classify_model import fallback
    from passing.qc_filter import (
        ClinicalFeatureExtractor,
        FACE_OVAL,
        INSIGHTFACE_DET_SIZE,
        LEFT_JAW_LINE,
        LEFT_MALAR,
        LEFT_ORBITAL,
        LEFT_TEMPORAL,
        MODEL_PATH,
        RIGHT_JAW_LINE,
        RIGHT_MALAR,
        RIGHT_ORBITAL,
        RIGHT_TEMPORAL,
    )

ROI_NAMES = ("temporal", "orbital", "malar", "jawline")
ROI_COLORS = {
    "temporal": (255, 80, 80),
    "orbital": (80, 255, 255),
    "malar": (80, 180, 255),
    "jawline": (100, 255, 100),
}
LANDMARK_MODEL_PATH = Path(__file__).resolve().parent / "passing" / "face_landmarker.task"
if not LANDMARK_MODEL_PATH.exists():
    LANDMARK_MODEL_PATH = Path(MODEL_PATH)
ViewName = str
ROIMasks = Dict[str, np.ndarray]


def _normalize_for_vis(attn_map: np.ndarray) -> np.ndarray:
    arr = np.asarray(attn_map, dtype=np.float32)
    return (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)


def _to_uint8_rgb(image: Union[Image.Image, np.ndarray]) -> np.ndarray:
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGB"), dtype=np.uint8)

    arr = np.asarray(image)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("image must be an RGB PIL image or an HxWx3 numpy array")
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return arr


def _canonical_view_name(view_name: ViewName) -> str:
    aliases = {
        "front": "front",
        "left": "left_45",
        "left_45": "left_45",
        "right": "right_45",
        "right_45": "right_45",
    }
    return aliases.get((view_name or "front").lower(), "front")


class ClassSpecificGradientRollout:
    """Positive-class gradient-weighted rollout for CLIP visual ViT attention."""

    def __init__(self, model, class_names=CLASS_NAMES, device: str = DEVICE):
        self.model = model
        self.class_names = list(class_names)
        self.device = device
        self.attn_modules = list(self.model.clip.visual.transformer.resblocks)
        missing = [
            idx
            for idx, block in enumerate(self.attn_modules)
            if not hasattr(block.attn, "capture_attention")
        ]
        if missing:
            raise RuntimeError(
                "当前可视化需要 LoRA attention 的 capture_attention 支持；"
                f"以下block不支持: {missing[:5]}"
            )

    def _set_capture(self, enabled: bool) -> None:
        for block in self.attn_modules:
            block.attn.capture_attention = enabled
            block.attn.captured_attn = None

    @staticmethod
    def _normalize_rows(mat: torch.Tensor) -> torch.Tensor:
        return mat / mat.sum(dim=-1, keepdim=True).clamp_min(1e-8)

    def _rollout_nonnegative(self, cams) -> np.ndarray:
        if not cams:
            raise RuntimeError("没有捕获到可用于解释的attention梯度。")

        n_tokens = cams[0].shape[-1]
        result = torch.eye(n_tokens, dtype=cams[0].dtype)
        for cam in cams:
            cam = torch.clamp(cam, min=0)
            cam = cam + torch.eye(n_tokens, dtype=cam.dtype)
            cam = self._normalize_rows(cam)
            result = torch.matmul(cam, result)

        cls_attention = result[0, 1:]
        grid_size = int(np.sqrt(cls_attention.numel()))
        if grid_size * grid_size != cls_attention.numel():
            raise RuntimeError(f"patch token数量不是平方数: {cls_attention.numel()}")
        return cls_attention.reshape(grid_size, grid_size).numpy()

    def __call__(
        self,
        image_tensor: torch.Tensor,
        target_class: str = POSITIVE_CLASS,
    ) -> Dict[str, object]:
        """Return the attention map for the fixed ``malnourished_face`` target."""

        if target_class != POSITIVE_CLASS:
            raise ValueError(f"target_class is fixed to {POSITIVE_CLASS!r}")
        target_idx = self.class_names.index(POSITIVE_CLASS)

        self.model.zero_grad(set_to_none=True)
        image_tensor = image_tensor.detach().clone().to(self.device).requires_grad_(True)

        self._set_capture(True)
        try:
            with torch.enable_grad():
                logits = self.model(image_tensor)
                probs = torch.softmax(logits, dim=1)

                if logits.shape[1] == 2:
                    other_idx = 1 - target_idx
                    score = logits[:, target_idx] - logits[:, other_idx]
                else:
                    score = logits[:, target_idx]
                score.sum().backward()

            pos_cams = []
            for block in self.attn_modules:
                attn = block.attn.captured_attn
                if attn is None or attn.grad is None:
                    continue
                grad = attn.grad.detach()
                attn_value = attn.detach()
                pos_cams.append((attn_value * torch.relu(grad)).mean(dim=1)[0].cpu())

            attn_map = self._rollout_nonnegative(pos_cams)
            return {
                "attn_map": attn_map,
                "maps": {"pos": attn_map},
                "logits": logits.detach().cpu().squeeze(0).numpy(),
                "probs": probs.detach().cpu().squeeze(0).numpy(),
                "target_idx": target_idx,
                "target_class": target_class,
            }
        finally:
            self._set_capture(False)
            self.model.zero_grad(set_to_none=True)


class DynamicROIAttentionAnalyzer:
    """Generate clinical ROI masks with view-specific landmark extraction knobs."""

    def __init__(self, use_insightface_fallback: bool = False):
        self.extractors: Dict[Tuple[str, Optional[str]], ClinicalFeatureExtractor] = {}
        self.use_insightface_fallback = bool(use_insightface_fallback)

    def _extractor_for_view(self, view_name: ViewName) -> ClinicalFeatureExtractor:
        view_name = _canonical_view_name(view_name)
        if view_name == "front":
            key = ("front", None)
            kwargs = dict(
                use_insightface_fallback=self.use_insightface_fallback,
                insightface_det_sizes=(INSIGHTFACE_DET_SIZE,),
                insightface_crop_expands=(1.30, 1.60, 1.90),
                insightface_det_thresh=0.35,
                insightface_primary=False,
                view_hint="front",
                side_hint=None,
            )
        elif view_name == "left_45":
            key = ("three_quarter", "left")
            kwargs = dict(
                use_insightface_fallback=self.use_insightface_fallback,
                insightface_det_sizes=(INSIGHTFACE_DET_SIZE,),
                insightface_crop_expands=(1.45, 1.70, 2.00),
                insightface_det_thresh=0.30,
                insightface_primary=True,
                mp_min_face_detection_confidence=0.25,
                mp_min_face_presence_confidence=0.25,
                mp_min_tracking_confidence=0.25,
                view_hint="three_quarter",
                side_hint="left",
            )
        else:
            key = ("three_quarter", "right")
            kwargs = dict(
                use_insightface_fallback=self.use_insightface_fallback,
                insightface_det_sizes=(INSIGHTFACE_DET_SIZE,),
                insightface_crop_expands=(1.45, 1.70, 2.00),
                insightface_det_thresh=0.30,
                insightface_primary=True,
                mp_min_face_detection_confidence=0.25,
                mp_min_face_presence_confidence=0.25,
                mp_min_tracking_confidence=0.25,
                view_hint="three_quarter",
                side_hint="right",
            )

        if key not in self.extractors:
            self.extractors[key] = ClinicalFeatureExtractor(str(LANDMARK_MODEL_PATH), **kwargs)
        return self.extractors[key]

    def _roi_masks_from_landmarks(self, extractor: ClinicalFeatureExtractor, image_np: np.ndarray, landmarks) -> ROIMasks:
        l_temp = extractor.get_mask_from_points(image_np.shape, landmarks[LEFT_TEMPORAL], mode="hull")
        r_temp = extractor.get_mask_from_points(image_np.shape, landmarks[RIGHT_TEMPORAL], mode="hull")
        l_orb = extractor.get_mask_from_points(image_np.shape, landmarks[LEFT_ORBITAL], mode="hull")
        r_orb = extractor.get_mask_from_points(image_np.shape, landmarks[RIGHT_ORBITAL], mode="hull")
        l_malar = extractor.get_mask_from_points(image_np.shape, landmarks[LEFT_MALAR], mode="hull")
        r_malar = extractor.get_mask_from_points(image_np.shape, landmarks[RIGHT_MALAR], mode="hull")
        l_jaw = extractor.get_mask_from_points(image_np.shape, landmarks[LEFT_JAW_LINE], mode="line", thickness=15)
        r_jaw = extractor.get_mask_from_points(image_np.shape, landmarks[RIGHT_JAW_LINE], mode="line", thickness=15)

        return {
            "temporal": np.maximum(l_temp, r_temp),
            "orbital": np.maximum(l_orb, r_orb),
            "malar": np.maximum(l_malar, r_malar),
            "jawline": np.maximum(l_jaw, r_jaw),
        }

    def _face_mask_from_landmarks(self, extractor: ClinicalFeatureExtractor, image_np: np.ndarray, landmarks) -> Optional[np.ndarray]:
        face_mask = extractor.get_mask_from_points(
            image_np.shape,
            landmarks[FACE_OVAL],
            mode="hull",
        )
        if not np.any(face_mask):
            return None
        return face_mask

    def generate_roi_masks(self, image_np: np.ndarray, view_name: ViewName = "front") -> Optional[ROIMasks]:
        image_np = _to_uint8_rgb(image_np)
        extractor = self._extractor_for_view(view_name)
        landmarks = extractor.get_landmarks(image_np)
        if landmarks is None:
            return None
        return self._roi_masks_from_landmarks(extractor, image_np, landmarks)

    def generate_face_mask(self, image_np: np.ndarray, view_name: ViewName = "front") -> Optional[np.ndarray]:
        image_np = _to_uint8_rgb(image_np)
        extractor = self._extractor_for_view(view_name)
        landmarks = extractor.get_landmarks(image_np)
        if landmarks is None:
            return None
        return self._face_mask_from_landmarks(extractor, image_np, landmarks)

    def generate_roi_and_face_masks(
        self,
        image_np: np.ndarray,
        view_name: ViewName = "front",
    ) -> Optional[Tuple[ROIMasks, np.ndarray]]:
        image_np = _to_uint8_rgb(image_np)
        extractor = self._extractor_for_view(view_name)
        landmarks = extractor.get_landmarks(image_np)
        if landmarks is None:
            return None

        roi_masks = self._roi_masks_from_landmarks(extractor, image_np, landmarks)
        face_mask = self._face_mask_from_landmarks(extractor, image_np, landmarks)
        if face_mask is None:
            return None
        return roi_masks, face_mask


def compute_roi_map_scores(attn_map: np.ndarray, roi_masks: Mapping[str, np.ndarray]) -> Dict[str, object]:
    """Compute ROI enrichment as ROI mean attention divided by global mean attention."""

    scores: Dict[str, object] = {}
    attn_map = np.asarray(attn_map, dtype=np.float32)
    best_roi = None
    best_enrichment = -np.inf

    for roi_name, mask in roi_masks.items():
        mask = np.asarray(mask)
        attn_resized = cv2.resize(
            attn_map,
            (mask.shape[1], mask.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        )
        mask_bool = mask > 0
        if not np.any(mask_bool):
            roi_mean = 0.0
            enrichment = 0.0
        else:
            roi_mean = float(np.mean(attn_resized[mask_bool]))
            global_attention = float(np.mean(attn_resized))
            enrichment = float(roi_mean / (global_attention + 1e-8))

        scores[f"roi_{roi_name}_mean"] = roi_mean
        scores[f"roi_{roi_name}_enrichment"] = enrichment
        if enrichment > best_enrichment:
            best_roi = roi_name
            best_enrichment = enrichment

    scores["focused_roi"] = best_roi
    scores["focused_roi_enrichment"] = None if best_roi is None else float(best_enrichment)
    return scores


def compute_face_normalized_roi_map_scores(
    attn_map: np.ndarray,
    roi_masks: Mapping[str, np.ndarray],
    face_mask: Optional[np.ndarray],
    eps: float = 1e-8,
) -> Dict[str, object]:
    """Compute ROI enrichment using the detected face as the baseline."""

    scores: Dict[str, object] = {}
    if face_mask is None or not np.any(face_mask):
        for roi_name in roi_masks:
            scores[f"roi_{roi_name}_face_mean"] = None
            scores[f"roi_{roi_name}_face_enrichment"] = None
        return scores

    attn_map = np.asarray(attn_map, dtype=np.float32)
    face_mask = np.asarray(face_mask)
    attn_resized = cv2.resize(
        attn_map,
        (face_mask.shape[1], face_mask.shape[0]),
        interpolation=cv2.INTER_LINEAR,
    )
    face_bool = face_mask > 0
    if not np.any(face_bool):
        for roi_name in roi_masks:
            scores[f"roi_{roi_name}_face_mean"] = None
            scores[f"roi_{roi_name}_face_enrichment"] = None
        return scores

    face_attention = float(np.mean(attn_resized[face_bool]))
    best_roi = None
    best_enrichment = -np.inf
    for roi_name, mask in roi_masks.items():
        mask = np.asarray(mask)
        roi_face_bool = (mask > 0) & face_bool
        if not np.any(roi_face_bool):
            roi_face_mean = None
            enrichment = None
        else:
            roi_face_mean = float(np.mean(attn_resized[roi_face_bool]))
            enrichment = float(roi_face_mean / (face_attention + eps))

        scores[f"roi_{roi_name}_face_mean"] = roi_face_mean
        scores[f"roi_{roi_name}_face_enrichment"] = enrichment
        if enrichment is not None and enrichment > best_enrichment:
            best_roi = roi_name
            best_enrichment = enrichment

    scores["focused_face_roi"] = best_roi
    scores["focused_face_roi_enrichment"] = None if best_roi is None else float(best_enrichment)
    return scores


def draw_roi_visualization(
    image: Union[Image.Image, np.ndarray],
    roi_masks: Mapping[str, np.ndarray],
    alpha: float = 0.3,
    return_base64: bool = False,
    image_format: str = "PNG",
) -> Union[Image.Image, str]:
    """Return one RGB image containing the original image with clinical ROI overlays."""

    roi_vis = _to_uint8_rgb(image).copy()
    alpha = float(np.clip(alpha, 0.0, 1.0))
    for roi_name, mask in roi_masks.items():
        if roi_name not in ROI_COLORS:
            continue
        mask_bool = np.asarray(mask) > 0
        if not np.any(mask_bool):
            continue
        color = np.array(ROI_COLORS[roi_name], dtype=np.float32)
        roi_vis[mask_bool] = ((1.0 - alpha) * roi_vis[mask_bool] + alpha * color).astype(np.uint8)

    pil_image = Image.fromarray(roi_vis)
    if not return_base64:
        return pil_image

    buffer = io.BytesIO()
    pil_image.save(buffer, format=image_format)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/{image_format.lower()};base64,{encoded}"


def draw_visualization(
    image: Union[Image.Image, np.ndarray],
    attn_map: Optional[np.ndarray] = None,
    maps: Optional[Mapping[str, np.ndarray]] = None,
    alpha: float = 0.5,
    return_base64: bool = False,
    image_format: str = "PNG",
) -> Union[Image.Image, str]:
    """Return one RGB image containing the original image with heatmap overlay."""

    img_np = _to_uint8_rgb(image)
    if attn_map is None:
        if maps is None or "pos" not in maps:
            raise ValueError("attn_map or maps['pos'] is required")
        attn_map = maps["pos"]

    heat = _normalize_for_vis(np.asarray(attn_map, dtype=np.float32))
    heat_resized = cv2.resize(heat, (img_np.shape[1], img_np.shape[0]), interpolation=cv2.INTER_LINEAR)
    heatmap = cv2.applyColorMap((heat_resized * 255).astype(np.uint8), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)

    alpha = float(np.clip(alpha, 0.0, 1.0))
    overlay = ((1.0 - alpha) * img_np + alpha * heatmap).astype(np.uint8)
    pil_image = Image.fromarray(overlay)

    if not return_base64:
        return pil_image

    buffer = io.BytesIO()
    pil_image.save(buffer, format=image_format)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/{image_format.lower()};base64,{encoded}"
