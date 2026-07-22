"""调用 Qwen 生成营养筛查辅助建议，并仅传输去标识化、面向决策的摘要。"""
import json
import re
from typing import Any, Dict, List
from urllib import error, request

from fastapi import HTTPException

from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL, QWEN_TIMEOUT_SECONDS

_SYSTEM_PROMPT = """你是营养筛查系统的辅助分析助手。仅依据输入的结构化筛查摘要，以中文给出一般性营养管理建议。
所有输入均为筛查信息，只能用于提示营养风险，不能用于判定患者营养状况。你的角色是健康教育与随访支持，不得作出诊断、处方、用药、补充剂或精确摄入剂量建议，不得捏造未提供的数据，也不得替代医生或临床营养师。
分析顺序：先提炼可验证的筛查事实；说明不同筛查工具的风险提示是否一致；再给出按优先级排列的低风险、可执行建议。GLIM、NRS-2002、MNA-SF 是主要筛查依据；面部图像筛查仅作辅助风险信号。不得将任何单项或组合筛查结果表述为营养状况的最终判定。
重点发现必须引用输入中的具体事实或数值。建议应避免疾病专属饮食限制；若缺少合并症、器官功能、吞咽咀嚼、胃肠症状、过敏和饮食偏好等信息，应明确列为需要补充的信息。
只输出 JSON，字段为 summary、key_findings、suggestions、follow_up、missing_information。key_findings、suggestions、follow_up、missing_information 必须是字符串数组；重点发现最多 3 条，建议行动 3 至 5 条，随访建议最多 3 条，每条不超过 120 字。"""


def _as_list(value: Any, limit: int = 5) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:160] for item in value if str(item).strip()][:limit]


def _as_text(value: Any, fallback: str, limit: int = 500) -> str:
    text = str(value).strip() if value is not None else ""
    return text[:limit] if text else fallback


def _extract_json(content: str, urgent_signs: List[str]) -> Dict[str, Any]:
    if not isinstance(content, str):
        raise HTTPException(status_code=502, detail="Qwen 未返回可用文本，请重新生成。")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content.strip(), re.DOTALL)
    try:
        raw = json.loads(fenced.group(1) if fenced else content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Qwen 返回格式异常，请重新生成。") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="Qwen 返回格式异常，请重新生成。")
    return {
        "summary": _as_text(raw.get("summary"), "暂未生成综合摘要。", 200),
        "key_findings": _as_list(raw.get("key_findings"), 3),
        "suggestions": _as_list(raw.get("suggestions"), 5),
        "follow_up": _as_list(raw.get("follow_up"), 3) or ["建议结合实际情况咨询医生或临床营养师。"],
        # 由后端根据确定的筛查结果生成，避免模型凭空编造紧急风险。
        "urgent_signs": urgent_signs,
        "missing_information": _as_list(raw.get("missing_information"), 5),
        "disclaimer": "本内容基于营养筛查结果生成，仅作健康教育与随访辅助参考；所有量表和图像结果均为风险提示，不能判定营养状况，不构成诊断、治疗或用药建议。",
    }


def _result(value: object) -> Dict[str, object]:
    return value if isinstance(value, dict) else {}


def _deidentified_summary(draft: Dict[str, object]) -> Dict[str, object]:
    """只发送建议所需的去标识化指标，不传姓名、图片、文件路径、原始概率或报告文本。"""
    patient = _result(draft.get("patient_info"))
    nrs = _result(draft.get("nrs2002_result"))
    mna = _result(draft.get("mnasf_result"))
    image = _result(draft.get("image_result"))
    glim = _result(draft.get("glim_result"))
    prediction = {
        "malnourished": "营养不良风险",
        "normal": "营养状态正常",
    }.get(image.get("prediction"), "未完成或无法判断")
    sex = {"male": "男", "female": "女"}.get(patient.get("gender"), patient.get("gender"))

    return {
        "基本信息": {
            "年龄": patient.get("age"),
            "生理性别": sex,
            "身高_cm": patient.get("height"),
            "小腿围_cm": patient.get("calfCircumference"),
        },
        "体重与摄食趋势": {
            "体重记录_kg": draft.get("weight_records") or {},
            "近四周摄食量_正常需求百分比": draft.get("intake_records") or {},
            "当前BMI": nrs.get("bmi") or glim.get("bmi"),
            "近期体重下降百分比": nrs.get("weight_loss_details") or {},
            "GLIM体重下降百分比": {
                "6个月内": glim.get("weight_loss_6m_pct"),
                "6个月以上": glim.get("weight_loss_over6m_pct"),
            },
        },
        "NRS_2002": {
            "总分": nrs.get("total_score"),
            "营养风险": nrs.get("risk_level"),
            "营养状态受损分": nrs.get("nutrition_score"),
            "疾病严重程度分": nrs.get("disease_score"),
            "年龄分": nrs.get("age_score"),
        },
        "MNA_SF": {
            "总分_14分": mna.get("total_score"),
            "结论": mna.get("level"),
        },
        "GLIM": {
            "筛查提示营养不良风险": glim.get("is_malnourished"),
            "严重程度": glim.get("severity"),
            "表型标准": glim.get("phenotypic_criteria_triggered") or [],
            "病因学标准": glim.get("etiological_criteria_triggered") or [],
        },
        "面部图像筛查_仅辅助证据": {
            "结论": prediction,
            "归一化分值_7分": image.get("sga_normalized_score"),
        },
        "建议前仍需补充的临床信息": [
            "基础疾病及器官功能限制（如肾、心、肝功能和糖代谢情况）",
            "吞咽、咀嚼困难及胃肠道症状",
            "食物过敏、饮食偏好、文化习惯和获取食物的条件",
            "当前治疗、药物及由医生或营养师制定的饮食限制",
        ],
    }


def _professional_review_alerts(draft: Dict[str, object]) -> List[str]:
    """只根据确定的量表结论生成需尽快专业评估提示，不让模型自由判断紧急程度。"""
    nrs = _result(draft.get("nrs2002_result"))
    glim = _result(draft.get("glim_result"))
    alerts = []
    if glim.get("is_malnourished"):
        severity = glim.get("severity")
        message = "GLIM 筛查提示营养不良风险"
        if severity:
            message += "（" + str(severity) + "）"
        alerts.append(message + "，建议尽快由医生或临床营养师进一步评估。")
    elif nrs.get("has_risk"):
        alerts.append("NRS-2002 提示存在营养风险，建议尽快安排营养专业人员随访。")
    return alerts


def generate_personalized_analysis(draft: Dict[str, object]) -> Dict[str, object]:
    """经百炼 OpenAI 兼容接口请求 Qwen，且不向前端泄露上游错误细节。"""
    if not QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="尚未配置 Qwen 服务。请在后端设置 DASHSCOPE_API_KEY 后重启服务。")
    payload = {
        "model": QWEN_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "以下是去标识化且已压缩的筛查摘要：\n"
                + json.dumps(_deidentified_summary(draft), ensure_ascii=False),
            },
        ],
    }
    http_request = request.Request(
        QWEN_BASE_URL + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + QWEN_API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=QWEN_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode())
        content = result["choices"][0]["message"]["content"]
    except error.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Qwen 服务请求失败，请稍后重试。") from exc
    except (error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="暂时无法连接 Qwen 服务，请稍后重试。") from exc
    return {
        "model": QWEN_MODEL,
        "analysis": _extract_json(content, _professional_review_alerts(draft)),
    }
