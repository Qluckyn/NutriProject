"""Lightweight narrative text for ROI attention results."""

ROI_CN_NAMES = {
    "temporal": "颞部",
    "orbital": "眶周",
    "malar": "颧颊",
    "jawline": "下颌缘",
}
ATTENDED_THRESHOLD = 1.15


def build_attention_text(roi_scores: dict, attended_threshold: float = ATTENDED_THRESHOLD) -> str:
    # roi_scores: {"temporal": enrichment, "orbital": ..., "malar": ..., "jawline": ...}
    attended = [roi for roi, value in roi_scores.items() if value > attended_threshold]
    if not attended:
        return "未见关注度显著高于阈值的预设区域"
    return "，".join(f"对{ROI_CN_NAMES[roi]}区域关注度较高" for roi in attended)
