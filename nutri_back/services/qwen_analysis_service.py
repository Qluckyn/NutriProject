"""调用 Qwen 生成营养筛查辅助建议，并限制传输为去标识化结构化数据。"""
import json
import re
from typing import Any, Dict, List
from urllib import error, request

from fastapi import HTTPException
from config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL, QWEN_TIMEOUT_SECONDS

_SYSTEM_PROMPT = """你是营养筛查系统的辅助分析助手。仅依据输入数据，以中文给出一般性营养管理建议。
不得作出诊断、处方、用药或剂量建议，不得捏造数据，不得替代医生或营养师。
只输出 JSON：summary、key_findings、suggestions、follow_up、urgent_signs、disclaimer；其中三个复数项必须为字符串数组。"""


def _as_list(value: Any) -> List[str]:
    """限制模型列表长度，避免异常长输出直接进入页面。"""
    return [str(item).strip() for item in value if str(item).strip()][:5] if isinstance(value, list) else []


def _as_text(value: Any, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text[:500] if text else fallback


def _extract_json(content: str) -> Dict[str, Any]:
    if not isinstance(content, str):
        raise HTTPException(status_code=502, detail="Qwen 未返回可用文本，请重新生成。")
    """兼容模型可能包裹在 Markdown 代码块中的 JSON，并完成字段兜底。"""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content.strip(), re.DOTALL)
    try:
        raw = json.loads(fenced.group(1) if fenced else content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Qwen 返回格式异常，请重新生成。") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="Qwen 返回格式异常，请重新生成。")
    return {
        "summary": _as_text(raw.get("summary"), "暂未生成综合摘要。"),
        "key_findings": _as_list(raw.get("key_findings")),
        "suggestions": _as_list(raw.get("suggestions")),
        "follow_up": _as_text(raw.get("follow_up"), "建议结合实际情况咨询医生或临床营养师。"),
        "urgent_signs": _as_list(raw.get("urgent_signs")),
        "disclaimer": _as_text(raw.get("disclaimer"), "本内容仅作营养筛查辅助参考，不构成诊断、治疗或用药建议。"),
    }


def _deidentified_summary(draft: Dict[str, object]) -> Dict[str, object]:
    """不发送姓名、原始图片、文件名等直接身份标识，只发送筛查所需信息。"""
    patient = draft.get("patient_info") if isinstance(draft.get("patient_info"), dict) else {}
    return {
        "基本信息": {"年龄": patient.get("age"), "性别": patient.get("gender"), "身高_cm": patient.get("height"), "小腿围_cm": patient.get("calfCircumference")},
        "体重记录_kg": draft.get("weight_records") or {}, "摄食记录_正常需求百分比": draft.get("intake_records") or {},
        "NRS_2002": draft.get("nrs2002_result"), "MNA_SF": draft.get("mnasf_result"),
        "面部图像筛查结果": draft.get("image_result"), "GLIM": draft.get("glim_result"),
    }


def generate_personalized_analysis(draft: Dict[str, object]) -> Dict[str, object]:
    """经百炼 OpenAI 兼容接口请求 Qwen，且不向前端泄露上游错误细节。"""
    if not QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="尚未配置 Qwen 服务。请在后端设置 DASHSCOPE_API_KEY 后重启服务。")
    payload = {"model": QWEN_MODEL, "temperature": 0.2, "messages": [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "以下是去标识化的筛查数据：\n" + json.dumps(_deidentified_summary(draft), ensure_ascii=False)},
    ]}
    http_request = request.Request(f"{QWEN_BASE_URL}/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(http_request, timeout=QWEN_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode())
        content = result["choices"][0]["message"]["content"]
    except error.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Qwen 服务请求失败，请稍后重试。") from exc
    except (error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="暂时无法连接 Qwen 服务，请稍后重试。") from exc
    return {"model": QWEN_MODEL, "analysis": _extract_json(content)}
