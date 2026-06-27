from typing import Dict, List, Tuple

from fastapi import HTTPException

from config import GLIM_CHRONIC_DISEASE_IDS, REQUIRED_GLIM_MONTHS, REQUIRED_NRS_MONTHS
from model_loader import round4
from schemas.assess_schemas import GLIMRequest, MNASFRequest, NRS2002Request
from services.diseases_service import (
    get_disease_map,
    get_glim_inflammation_config,
    get_glim_intake_config,
    get_nrs_disease_map,
    option_map,
)

# 三个临床营养评估量表的校验与计算逻辑集中在此模块。


def raise_zh_422(message: str) -> None:
    raise HTTPException(status_code=422, detail=message)


def validate_weight_records(records: Dict[str, float], required_months: Tuple[str, ...]) -> None:
    """校验必填月份体重，避免除零和缺失字段影响评分。"""
    missing = [month for month in required_months if month not in records or records[month] is None]
    if missing:
        raise_zh_422("缺少必填体重记录：" + "、".join(f"距今{month}个月" for month in missing))
    invalid = [month for month, value in records.items() if value is None or float(value) <= 0]
    if invalid:
        raise_zh_422("体重必须为大于0的数字：" + "、".join(f"距今{month}个月" for month in invalid))


def validate_disease_ids(disease_ids: List[str]) -> None:
    disease_map = get_disease_map()
    unknown = [item for item in disease_ids if item not in disease_map]
    if unknown:
        raise_zh_422("疾病id不存在：" + "、".join(unknown))


def calc_bmi(weight: float, height_cm: float) -> float:
    if height_cm <= 0:
        raise_zh_422("身高必须大于0。")
    return float(weight) / ((float(height_cm) / 100) ** 2)


def calc_loss_pct(records: Dict[str, float], month: str) -> float:
    """按距今月份计算相对当前体重的下降百分比。"""
    previous = float(records[month])
    current = float(records["0"])
    if previous <= 0:
        raise_zh_422(f"距今{month}个月体重必须大于0。")
    return (previous - current) / previous * 100


def nrs_nutrition_score(payload: NRS2002Request) -> Tuple[int, Dict[str, float], float]:
    records = payload.weight_records
    loss_1m = calc_loss_pct(records, "1")
    loss_2m = calc_loss_pct(records, "2")
    loss_3m = calc_loss_pct(records, "3")

    weight_score = 0
    # if loss_1m > 5 and payload.general_condition_impaired:
    if loss_1m > 5:
        weight_score = 3
    # elif loss_2m > 5 and payload.general_condition_impaired:
    elif loss_2m > 5:
        weight_score = 2
    elif loss_3m > 5:
        weight_score = 1

    bmi = calc_bmi(records["0"], payload.height)
    bmi_score = 0
    if bmi < 18.5 and payload.general_condition_impaired:
        bmi_score = 3
    elif 18.5 <= bmi <= 20.5 and payload.general_condition_impaired:
        bmi_score = 2

    intake = payload.intake_last_week
    if intake <= 25:
        intake_score = 3
    elif intake <= 50:
        intake_score = 2
    elif intake <= 75:
        intake_score = 1
    else:
        intake_score = 0

    details = {
        "1m_loss_pct": round4(loss_1m),
        "2m_loss_pct": round4(loss_2m),
        "3m_loss_pct": round4(loss_3m),
    }
    return max(weight_score, bmi_score, intake_score), details, bmi


def disease_score_for_nrs(disease_ids: List[str]) -> int:
    disease_map = get_nrs_disease_map()
    if not disease_ids:
        return 0
    return max(int(disease_map[item].get("nrs_score", 0)) for item in disease_ids)


def assess_nrs2002(payload: NRS2002Request) -> Dict[str, object]:
    validate_weight_records(payload.weight_records, REQUIRED_NRS_MONTHS)
    unknown_nrs_ids = [item for item in payload.disease_ids if item not in get_nrs_disease_map()]
    if unknown_nrs_ids:
        raise_zh_422("NRS-2002疾病id不存在：" + "、".join(unknown_nrs_ids))

    nutrition_score, loss_details, bmi = nrs_nutrition_score(payload)
    disease_score = disease_score_for_nrs(payload.disease_ids)
    age_score = 1 if payload.age >= 70 else 0
    total_score = nutrition_score + disease_score + age_score
    # NRS-2002判定规则：总分>=3为存在营养风险，否则暂无营养风险。
    has_risk = total_score >= 3
    risk_level = "存在营养风险" if has_risk else "暂无营养风险"
    recommendation = (
        "建议启动营养支持流程，结合临床情况完善膳食评估、实验室检查和个体化营养干预。"
        if has_risk
        else "建议继续常规饮食管理与动态随访，如体重或摄食量下降应及时复评。"
    )

    return {
        "tool": "NRS-2002",
        "total_score": total_score,
        "nutrition_score": nutrition_score,
        "disease_score": disease_score,
        "age_score": age_score,
        "bmi": round4(bmi),
        "weight_loss_details": loss_details,
        "has_risk": has_risk,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "message": f"NRS-2002总分为{total_score}分，判定为：{risk_level}。{recommendation}",
    }


def assess_mna_sf(payload: MNASFRequest) -> Dict[str, object]:
    required = ("0",) if "3" not in payload.weight_records else ("0", "3")
    validate_weight_records(payload.weight_records, required)
    if payload.use_bmi:
        bmi = calc_bmi(payload.weight_records["0"], payload.height)
    else:
        if payload.calf_circumference is None or payload.calf_circumference <= 0:
            raise_zh_422("使用小腿围评估时，小腿围为必填且必须大于0。")
        bmi = calc_bmi(payload.weight_records["0"], payload.height)

    q1 = 0 if payload.intake_last_week <= 33 else 1 if payload.intake_last_week <= 66 else 2

    if "3" not in payload.weight_records:
        loss_kg = 0.0
        q2 = 1
    else:
        loss_kg = float(payload.weight_records["3"]) - float(payload.weight_records["0"])
        if loss_kg > 3:
            q2 = 0
        elif loss_kg > 0:
            q2 = 2
        else:
            q2 = 3

    q3 = payload.mobility
    q4 = 0 if payload.stress_or_acute_disease else 2
    q5 = payload.mental_status
    if payload.use_bmi:
        if bmi < 19:
            q6 = 0
        elif bmi <= 21:
            q6 = 1
        elif bmi <= 23:
            q6 = 2
        else:
            q6 = 3
    else:
        q6 = 0 if float(payload.calf_circumference) < 31 else 3

    total = q1 + q2 + q3 + q4 + q5 + q6
    if total >= 12:
        level = "营养正常"
    elif total >= 8:
        level = "营养不良风险"
    else:
        level = "营养不良"

    return {
        "tool": "MNA-SF",
        "total_score": total,
        "score_breakdown": {
            "q1_appetite": q1,
            "q2_weight_loss": q2,
            "q3_mobility": q3,
            "q4_stress": q4,
            "q5_mental": q5,
            "q6_bmi_or_calf": q6,
        },
        "bmi": round4(bmi),
        "weight_loss_3m_kg": round4(loss_kg),
        "level": level,
        "message": f"MNA-SF总分为{total}/14分，评估等级为：{level}。建议结合病史和饮食记录进行持续营养管理。",
    }


def assess_glim(payload: GLIMRequest) -> Dict[str, object]:
    validate_weight_records(payload.weight_records, REQUIRED_GLIM_MONTHS)
    disease_map = get_disease_map()
    intake_config = get_glim_intake_config()
    inflammation_config = get_glim_inflammation_config()
    gi_labels = option_map(intake_config.get("gi_symptoms", []))
    nutrition_impact_labels = option_map(intake_config.get("related_diseases", []))
    acute_labels = option_map(inflammation_config.get("acute", []))
    chronic_labels = option_map(inflammation_config.get("chronic", []))
    validate_disease_ids([item for item in payload.disease_ids if item in disease_map])
    if payload.muscle_loss not in {"none", "mild_moderate", "severe"}:
        raise_zh_422("肌肉减少程度必须为 none、mild_moderate 或 severe。")

    bmi = calc_bmi(payload.weight_records["0"], payload.height)
    loss_6m = calc_loss_pct(payload.weight_records, "6")
    loss_over6m = calc_loss_pct(payload.weight_records, "12")

    phenotypic = []
    if loss_6m > 5 or loss_over6m > 10:
        phenotypic.append("非自主体重丢失")
    if (payload.age < 70 and bmi < 18.5) or (payload.age >= 70 and bmi < 20):
        phenotypic.append("低BMI")
    if payload.muscle_loss != "none":
        phenotypic.append("肌肉减少")

    etiological = []
    intake_reasons = []
    if payload.reduced_intake and not (
        payload.intake_under_50_over_1w
        or payload.any_intake_reduction_over_2w
        or payload.gi_symptoms
        or payload.nutrition_impact_conditions
    ):
        intake_reasons.append("摄食减少或消化吸收障碍")
    if payload.intake_under_50_over_1w:
        intake_reasons.append("摄入量≤50%能量需求超过一周")
    if payload.any_intake_reduction_over_2w:
        intake_reasons.append("任意摄入量减少超过2周")
    intake_reasons.extend(
        gi_labels[item]
        for item in payload.gi_symptoms
        if item in gi_labels
    )
    intake_reasons.extend(
        nutrition_impact_labels[item]
        for item in payload.nutrition_impact_conditions
        if item in nutrition_impact_labels
    )
    if intake_reasons:
        etiological.append("摄食减少或消化吸收障碍：" + "、".join(dict.fromkeys(intake_reasons)))

    inflammation_reasons = []
    for disease_id in payload.acute_disease_ids:
        if disease_id in acute_labels:
            inflammation_reasons.append("急性疾病或损伤：" + acute_labels[disease_id])
    for disease_id in payload.chronic_disease_ids:
        if disease_id not in chronic_labels:
            continue
        disease_name = chronic_labels[disease_id]
        if disease_id == "malignant_tumor":
            cancer_details = []
            if payload.cancer_site:
                cancer_details.append("具体部位" + payload.cancer_site)
            if payload.cancer_stage:
                cancer_details.append("癌症分期" + payload.cancer_stage)
            if payload.cancer_malnutrition_related is not None:
                cancer_details.append("疾病相关性营养不良病因" + ("是" if payload.cancer_malnutrition_related else "否"))
            suffix = " [" + "，".join(cancer_details) + "]" if cancer_details else ""
            inflammation_reasons.append("慢性或反复发作疾病：" + disease_name + suffix)
            continue
        inflammation_reasons.append("慢性或反复发作疾病：" + disease_name)
    # 兼容旧请求：旧 disease_ids 仅在属于图片表单列出的急/慢性疾病时进入病因标准。
    for disease_id in payload.disease_ids:
        if disease_id in acute_labels:
            inflammation_reasons.append("急性疾病或损伤：" + acute_labels[disease_id])
        elif disease_id in GLIM_CHRONIC_DISEASE_IDS and disease_id in disease_map:
            inflammation_reasons.append("慢性或反复发作疾病：" + disease_map[disease_id]["name"])
    if payload.crp != -1 and payload.crp >= 5:
        inflammation_reasons.append("炎症状态指标：CRP升高")
    if payload.il6 != -1 and payload.il6 >= 7:
        inflammation_reasons.append("炎症状态指标：IL-6C升高")
    if inflammation_reasons:
        etiological.append("炎症或疾病负担：" + "、".join(dict.fromkeys(inflammation_reasons)))

    phenotypic_met = bool(phenotypic)
    etiological_met = bool(etiological)
    is_malnourished = phenotypic_met and etiological_met

    severity = None
    if is_malnourished:
        severe = (
            loss_6m > 10
            or loss_over6m > 20
            or (payload.age < 70 and bmi < 18.5)
            or (payload.age >= 70 and bmi < 20)
            or payload.muscle_loss == "severe"
        )
        moderate = (
            5 <= loss_6m <= 10
            or 10 <= loss_over6m <= 20
            or (payload.age < 70 and 18.5 <= bmi < 20)
            or (payload.age >= 70 and 20 <= bmi < 22)
            or payload.muscle_loss == "mild_moderate"
        )
        if severe:
            severity = "重度营养不良（2期）"
        elif moderate:
            severity = "中度营养不良（1期）"

    if is_malnourished:
        message = f"GLIM标准提示营养不良，严重程度为{severity or '需结合临床进一步分期'}。"
    else:
        message = "当前未同时满足GLIM表型标准和病因标准，暂不诊断为营养不良，建议动态随访。"

    return {
        "tool": "GLIM",
        "is_malnourished": is_malnourished,
        "phenotypic_met": phenotypic_met,
        "etiological_met": etiological_met,
        "phenotypic_criteria_triggered": phenotypic,
        "etiological_criteria_triggered": etiological,
        "bmi": round4(bmi),
        "weight_loss_6m_pct": round4(loss_6m),
        "weight_loss_over6m_pct": round4(loss_over6m),
        "severity": severity,
        "message": message,
    }
