"""Lightweight narrative text for ROI face-normalized attention results."""

ROI_NAMES = ("temporal", "orbital", "malar", "jawline")
ROI_CN_NAMES = {
    "temporal": "颞部",
    "orbital": "眶周",
    "malar": "颧颊",
    "jawline": "下颌缘",
}
ATTENDED_THRESHOLD = 1.10
FACE_ENRICHMENT_KEY_TEMPLATE = "roi_{roi}_face_enrichment"


def extract_face_normalized_roi_scores(scores: dict) -> dict:
    """Return {roi: face-normalized enrichment} from flat face-normalized scores.

    Expected flat input comes from compute_face_normalized_roi_map_scores:
    {"roi_temporal_face_enrichment": ..., "roi_orbital_face_enrichment": ...}
    """

    roi_scores = {}
    for roi in ROI_NAMES:
        value = scores.get(FACE_ENRICHMENT_KEY_TEMPLATE.format(roi=roi))
        if value is not None:
            roi_scores[roi] = float(value)
    return roi_scores


def build_attention_text(roi_scores: dict, attended_threshold: float = ATTENDED_THRESHOLD) -> str:
    # roi_scores: {"temporal": face_enrichment, "orbital": ..., "malar": ..., "jawline": ...}
    attended = [roi for roi, value in roi_scores.items() if roi in ROI_CN_NAMES and value > attended_threshold]
    if not attended:
        return "未见关注度显著高于阈值的预设区域"
    return "，".join(f"对{ROI_CN_NAMES[roi]}区域关注度较高" for roi in attended)


def build_attention_text_from_face_normalized_scores(
    scores: dict,
    attended_threshold: float = ATTENDED_THRESHOLD,
) -> str:
    return build_attention_text(
        extract_face_normalized_roi_scores(scores),
        attended_threshold=attended_threshold,
    )
