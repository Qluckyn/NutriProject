from typing import Dict, List, Optional, Tuple

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

MIN_ADULT_WEIGHT_KG = 30
MAX_ADULT_WEIGHT_KG = 200


def raise_zh_422(message: str) -> None:
    raise HTTPException(status_code=422, detail=message)


def round1(value: float) -> float:
    return round(float(value), 1)


def validate_weight_records(records: Dict[str, float], required_months: Tuple[str, ...]) -> None:
    """校验必填月份体重，避免除零和缺失字段影响评分。"""
    missing = [month for month in required_months if month not in records or records[month] is None]
    if missing:
        raise_zh_422("缺少必填体重记录：" + "、".join(f"距今{month}个月" for month in missing))
    invalid = []
    for month, value in records.items():
        if value is None:
            invalid.append(month)
            continue
        weight = float(value)
        if weight < MIN_ADULT_WEIGHT_KG or weight > MAX_ADULT_WEIGHT_KG:
            invalid.append(month)
    if invalid:
        raise_zh_422(
            f"体重必须为{MIN_ADULT_WEIGHT_KG}到{MAX_ADULT_WEIGHT_KG}kg之间的数字："
            + "、".join(f"距今{month}个月" for month in invalid)
        )


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
    if previous < MIN_ADULT_WEIGHT_KG or previous > MAX_ADULT_WEIGHT_KG:
        raise_zh_422(f"距今{month}个月体重必须为{MIN_ADULT_WEIGHT_KG}到{MAX_ADULT_WEIGHT_KG}kg之间的数字。")
    return (previous - current) / previous * 100


def optional_loss_pct(records: Dict[str, float], month: str) -> Optional[float]:
    if month not in records or records[month] is None:
        return None
    return calc_loss_pct(records, month)


def intake_label(value: float) -> str:
    numeric = float(value)
    if numeric <= 25:
        return "占正常进食0 ~ 1/4"
    if numeric <= 50:
        return "占正常进食的1/4 ~ 1/2"
    if numeric <= 75:
        return "占正常进食的1/2 ~ 3/4"
    return "占正常进食的3/4以上"


def nrs_nutrition_score(payload: NRS2002Request) -> Tuple[int, Dict[str, Optional[float]], float, List[Dict[str, object]]]:
    records = payload.weight_records
    loss_1m = optional_loss_pct(records, "1")
    loss_2m = optional_loss_pct(records, "2")
    loss_3m = optional_loss_pct(records, "3")

    weight_score = 0
    weight_reason = "1/2/3个月前体重未填写，体重下降项不参与评分。"
    # if loss_1m > 5 and payload.general_condition_impaired:
    if loss_1m is not None and loss_1m > 5:
        weight_score = 3
        weight_reason = f"1个月体重下降{round1(loss_1m)}%，超过5%，触发3分。"
    # elif loss_2m > 5 and payload.general_condition_impaired:
    elif loss_2m is not None and loss_2m > 5:
        weight_score = 2
        weight_reason = f"2个月体重下降{round1(loss_2m)}%，超过5%，触发2分。"
    elif loss_3m is not None and loss_3m > 5:
        weight_score = 1
        weight_reason = f"3个月体重下降{round1(loss_3m)}%，超过5%，触发1分。"
    elif any(loss is not None for loss in (loss_1m, loss_2m, loss_3m)):
        parts = []
        if loss_1m is not None:
            parts.append(f"1个月{round1(loss_1m)}%")
        if loss_2m is not None:
            parts.append(f"2个月{round1(loss_2m)}%")
        if loss_3m is not None:
            parts.append(f"3个月{round1(loss_3m)}%")
        weight_reason = "已填写体重下降：" + "、".join(parts) + "，均未触发体重下降评分。"

    bmi = calc_bmi(records["0"], payload.height)
    bmi_score = 0
    if bmi < 18.5 and payload.general_condition_impaired:
        bmi_score = 3
        bmi_reason = f"BMI为{round1(bmi)}，低于18.5，且全身情况受损，触发3分。"
    elif 18.5 <= bmi <= 20.5 and payload.general_condition_impaired:
        bmi_score = 2
        bmi_reason = f"BMI为{round1(bmi)}，位于18.5-20.5，且全身情况受损，触发2分。"
    elif payload.general_condition_impaired:
        bmi_reason = f"BMI为{round1(bmi)}，未达到BMI受损评分区间。"
    else:
        bmi_reason = f"BMI为{round1(bmi)}，但全身情况未标记为受损，BMI项不加分。"

    intake = payload.intake_last_week
    if intake <= 25:
        intake_score = 3
        intake_reason = f"最近一周摄食量为{intake_label(intake)}，触发3分。"
    elif intake <= 50:
        intake_score = 2
        intake_reason = f"最近一周摄食量为{intake_label(intake)}，触发2分。"
    elif intake <= 75:
        intake_score = 1
        intake_reason = f"最近一周摄食量为{intake_label(intake)}，触发1分。"
    else:
        intake_score = 0
        intake_reason = f"最近一周摄食量为{intake_label(intake)}，未触发摄食量评分。"

    nutrition_score = max(weight_score, bmi_score, intake_score)
    details = {
        "1m_loss_pct": round1(loss_1m) if loss_1m is not None else None,
        "2m_loss_pct": round1(loss_2m) if loss_2m is not None else None,
        "3m_loss_pct": round1(loss_3m) if loss_3m is not None else None,
    }
    evidence = [
        {"label": "体重下降", "score": weight_score, "triggered": weight_score > 0, "reason": weight_reason},
        {"label": "BMI", "score": bmi_score, "triggered": bmi_score > 0, "reason": bmi_reason},
        {"label": "摄食量", "score": intake_score, "triggered": intake_score > 0, "reason": intake_reason},
        {"label": "最终采用", "score": nutrition_score, "triggered": nutrition_score > 0, "reason": f"营养状态受损分取体重下降、BMI、摄食量三项中的最高值：{nutrition_score}分。"},
    ]
    return nutrition_score, details, bmi, evidence


def disease_score_for_nrs(disease_ids: List[str]) -> int:
    disease_map = get_nrs_disease_map()
    if not disease_ids:
        return 0
    return max(int(disease_map[item].get("nrs_score", 0)) for item in disease_ids)


def nrs_disease_evidence(disease_ids: List[str], disease_score: int) -> List[Dict[str, object]]:
    disease_map = get_nrs_disease_map()
    if not disease_ids:
        return [{"label": "疾病严重程度", "score": 0, "triggered": False, "reason": "未选择NRS-2002疾病严重程度相关疾病，疾病项为0分。"}]
    selected = [disease_map[item] for item in disease_ids]
    selected_text = "、".join(f"{item['name']}（{int(item.get('nrs_score', 0))}分）" for item in selected)
    return [{"label": "疾病严重程度", "score": disease_score, "triggered": disease_score > 0, "reason": f"{selected_text}；疾病严重程度取最高值{disease_score}分。"}]


def nrs_age_evidence(age: int, age_score: int) -> List[Dict[str, object]]:
    if age_score:
        reason = f"年龄{age}岁，≥70岁，加1分。"
    else:
        reason = f"年龄{age}岁，<70岁，年龄项为0分。"
    return [{"label": "年龄", "score": age_score, "triggered": age_score > 0, "reason": reason}]


def assess_nrs2002(payload: NRS2002Request) -> Dict[str, object]:
    validate_weight_records(payload.weight_records, REQUIRED_NRS_MONTHS)
    unknown_nrs_ids = [item for item in payload.disease_ids if item not in get_nrs_disease_map()]
    if unknown_nrs_ids:
        raise_zh_422("NRS-2002疾病id不存在：" + "、".join(unknown_nrs_ids))

    nutrition_score, loss_details, bmi, nutrition_evidence = nrs_nutrition_score(payload)
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
        "bmi": round1(bmi),
        "weight_loss_details": loss_details,
        "score_evidence": {
            "nutrition": nutrition_evidence,
            "disease": nrs_disease_evidence(payload.disease_ids, disease_score),
            "age": nrs_age_evidence(payload.age, age_score),
        },
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

    q1 = 0 if payload.intake_last_week <= 25 else 1 if payload.intake_last_week <= 75 else 2
    q1_reason = f"最近一周摄食量为{intake_label(payload.intake_last_week)}，对应{q1}分。"

    if "3" not in payload.weight_records:
        loss_kg = 0.0
        q2 = 1
        q2_reason = "3个月前体重未填写，按体重下降未知计1分。"
    else:
        loss_kg = float(payload.weight_records["3"]) - float(payload.weight_records["0"])
        if loss_kg > 3:
            q2 = 0
            q2_reason = f"近3个月体重下降{round4(loss_kg)}kg，超过3kg，计0分。"
        elif loss_kg > 0:
            q2 = 2
            q2_reason = f"近3个月体重下降{round4(loss_kg)}kg，未超过3kg，计2分。"
        else:
            q2 = 3
            q2_reason = "近3个月体重未下降或增加，计3分。"

    mobility_labels = {0: "需长期卧床或坐轮椅", 1: "可下床但不能外出", 2: "可以外出"}
    q3 = payload.mobility
    q3_reason = f"活动能力为“{mobility_labels.get(q3, '未知')}”，计{q3}分。"

    q4 = 0 if payload.stress_or_acute_disease else 2
    q4_reason = "近3个月有心理创伤或急性疾病，计0分。" if payload.stress_or_acute_disease else "近3个月无心理创伤或急性疾病，计2分。"

    mental_labels = {0: "严重痴呆或抑郁", 1: "轻度痴呆", 2: "无问题"}
    q5 = payload.mental_status
    q5_reason = f"精神心理状况为“{mental_labels.get(q5, '未知')}”，计{q5}分。"

    if payload.use_bmi:
        if bmi < 19:
            q6 = 0
            q6_reason = f"BMI为{round1(bmi)}，低于19，计0分。"
        elif bmi <= 21:
            q6 = 1
            q6_reason = f"BMI为{round1(bmi)}，位于19-21，计1分。"
        elif bmi <= 23:
            q6 = 2
            q6_reason = f"BMI为{round1(bmi)}，位于21-23，计2分。"
        else:
            q6 = 3
            q6_reason = f"BMI为{round1(bmi)}，大于23，计3分。"
    else:
        if float(payload.calf_circumference) < 31:
            q6 = 0
            q6_reason = f"小腿围为{round4(payload.calf_circumference)}cm，低于31cm，计0分。"
        else:
            q6 = 3
            q6_reason = f"小腿围为{round4(payload.calf_circumference)}cm，≥31cm，计3分。"

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
        "score_evidence": [
            {"label": "摄食量", "score": q1, "triggered": q1 < 2, "reason": q1_reason},
            {"label": "近3个月体重下降", "score": q2, "triggered": q2 < 3, "reason": q2_reason},
            {"label": "活动能力", "score": q3, "triggered": q3 < 2, "reason": q3_reason},
            {"label": "心理创伤或急性疾病", "score": q4, "triggered": q4 == 0, "reason": q4_reason},
            {"label": "精神心理状况", "score": q5, "triggered": q5 < 2, "reason": q5_reason},
            {"label": "BMI/小腿围", "score": q6, "triggered": q6 < 3, "reason": q6_reason},
        ],
        "bmi": round1(bmi),
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
    loss_6m = optional_loss_pct(payload.weight_records, "6")
    loss_over6m = optional_loss_pct(payload.weight_records, "12")

    phenotypic = []
    if (loss_6m is not None and loss_6m > 5) or (loss_over6m is not None and loss_over6m > 10):
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
    if payload.crp is not None and payload.crp >= 5:
        inflammation_reasons.append("炎症状态指标：CRP升高")
    if payload.il6 is not None and payload.il6 >= 7:
        inflammation_reasons.append("炎症状态指标：IL-6升高")
    if inflammation_reasons:
        etiological.append("炎症或疾病负担：" + "、".join(dict.fromkeys(inflammation_reasons)))

    phenotypic_met = bool(phenotypic)
    etiological_met = bool(etiological)
    is_malnourished = phenotypic_met and etiological_met

    severity = None
    if is_malnourished:
        severe = (
            (loss_6m is not None and loss_6m > 10)
            or (loss_over6m is not None and loss_over6m > 20)
            or (payload.age < 70 and bmi < 18.5)
            or (payload.age >= 70 and bmi < 20)
            or payload.muscle_loss == "severe"
        )
        moderate = (
            (loss_6m is not None and 5 <= loss_6m <= 10)
            or (loss_over6m is not None and 10 <= loss_over6m <= 20)
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
        "bmi": round1(bmi),
        "weight_loss_6m_pct": round1(loss_6m) if loss_6m is not None else None,
        "weight_loss_over6m_pct": round1(loss_over6m) if loss_over6m is not None else None,
        "severity": severity,
        "message": message,
    }
