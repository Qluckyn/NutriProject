"""Server-authoritative SGA evaluation shared by API, DOCX, history and Excel exports."""

from __future__ import annotations

from typing import Any, Dict

_LEVELS = ("SGA-A级", "SGA-B级", "SGA-C级")
_LEVEL_WITH_DESCRIPTION = ("SGA-A级（营养状况正常）", "SGA-B级（轻~中度营养不良）", "SGA-C级（重度营养不良）")


def _grade_text(grade: int | None) -> str:
    return "未评估" if grade is None else _LEVELS[grade]


def _metric(title: str, grade: int | None, reason: str) -> Dict[str, Any]:
    return {"title": title, "grade": grade, "level": _grade_text(grade), "reason": reason}


def _weight_metric(records: Dict[str, Any]) -> Dict[str, Any]:
    try:
        current, six_months = float(records["0"]), float(records["6"])
    except (KeyError, TypeError, ValueError):
        return _metric("体重下降", None, "未填写：SGA体重下降项不勾选。")
    if current <= 0 or six_months <= 0:
        return _metric("体重下降", None, "未填写：SGA体重下降项不勾选。")
    loss = (six_months - current) / six_months * 100
    loss_text = f"6个月内体重丢失{max(0, round(loss, 1))}%"
    try:
        recovered = loss > 10 and current > float(records.get("1"))
    except (TypeError, ValueError):
        recovered = False
    if recovered:
        return _metric("体重下降", 0, f"{loss_text}，近1月内体重已恢复。")
    if loss < 5:
        return _metric("体重下降", 0, f"{loss_text}，近6个月内体重下降较少。")
    if loss <= 10:
        return _metric("体重下降", 1, f"{loss_text}，近6个月内体重下降达5%～10%。")
    return _metric("体重下降", 2, f"{loss_text}，近6个月内体重下降超过10%。")


def _intake_metric(records: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {100: (0, "摄食量为正常需求的3/4以上。"), 75: (1, "摄食量为正常需求的1/2～3/4。"), 50: (1, "摄食量为正常需求的1/4～1/2。"), 25: (2, "摄食量为正常需求的0～1/4。")}
    try:
        grade, reason = mapping[int(float(records.get("4")))]
    except (KeyError, TypeError, ValueError):
        return _metric("饮食改变", None, "未填写：SGA饮食改变项不勾选。")
    return _metric("饮食改变", grade, reason)


def _mapped_metric(title: str, value: Any, mapping: Dict[str, tuple[int, str]], missing: str) -> Dict[str, Any]:
    grade_reason = mapping.get(value)
    return _metric(title, grade_reason[0], grade_reason[1]) if grade_reason else _metric(title, None, missing)


def evaluate_sga(draft: Dict[str, Any], image_result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Calculate the eight SGA items and overall grade from one draft snapshot."""
    image_form = draft.get("image_screening_form") or {}
    mobility = (draft.get("mnasf_form") or {}).get("mobility")
    if mobility is None:
        mobility = ((draft.get("mnasf_result") or {}).get("score_breakdown") or {}).get("q3_mobility")
    try:
        score = float((image_result or {})["sga_normalized_score"])
        facial_grade = 0 if score < 3.5 else 1 if score < 6.3 else 2
        facial_reason = f"面部图像归一化分值：{round(score)}/7。"
    except (KeyError, TypeError, ValueError):
        facial_grade, facial_reason = None, "缺少面部图像分值，无法判定。"
    metrics = [
        _weight_metric(draft.get("weight_records") or {}), _intake_metric(draft.get("intake_records") or {}),
        _mapped_metric("胃肠道症状", image_form.get("giSymptoms"), {"none": (0, "无消化道症状。"), "mild_under_2w": (1, "轻度消化道症状持续不足2周。"), "severe_over_2w": (2, "重度消化道症状持续超过2周。")}, "未填写，无法判定。"),
        _mapped_metric("活动能力", str(mobility) if mobility is not None else None, {"2": (0, "无限制。"), "1": (1, "正常活动受限。"), "0": (2, "活动明显受限。")}, "未填写：SGA活动能力项不勾选。"),
        _mapped_metric("应激反应", image_form.get("stressResponse"), {"no_fever": (0, "无发热。"), "temp_37_to_39_3d": (1, "近3天体温在37℃～39℃之间波动。"), "temp_ge_39_over_3d": (2, "体温≥39℃持续3天以上。")}, "未填写，无法判定。"),
        _metric("皮下脂肪消耗", facial_grade, facial_reason), _metric("肌肉消耗", facial_grade, facial_reason),
        _mapped_metric("踝部水肿", image_form.get("ankleEdema"), {"none": (0, "无踝部水肿。"), "mild_moderate": (1, "轻度～中度踝部水肿。"), "severe": (2, "重度踝部水肿。")}, "未填写，无法判定。"),
    ]
    grades = [item["grade"] for item in metrics]
    assessed, c_count = sum(grade is not None for grade in grades), sum(grade == 2 for grade in grades)
    bc_count = sum(grade is not None and grade >= 1 for grade in grades)
    if assessed < len(metrics):
        return {"metrics": metrics, "code": "SGA评估信息不足", "level": "评估信息不足", "className": "good", "summary": f"已完成{assessed}/8项，需补全后分级。"}
    if c_count >= 5:
        return {"metrics": metrics, "code": _LEVELS[2], "level": _LEVEL_WITH_DESCRIPTION[2], "className": "risk", "summary": f"8项中{c_count}项为C级，符合重度营养不良判定。"}
    if bc_count >= 5:
        return {"metrics": metrics, "code": _LEVELS[1], "level": _LEVEL_WITH_DESCRIPTION[1], "className": "risk", "summary": f"8项中{bc_count}项为B或C级，符合轻~中度营养不良判定。"}
    return {"metrics": metrics, "code": _LEVELS[0], "level": _LEVEL_WITH_DESCRIPTION[0], "className": "good", "summary": "B或C级条目不足5项，未达到营养不良判定条件。"}
