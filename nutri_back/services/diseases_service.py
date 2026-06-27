import json
from typing import Any, Dict, List

from config import (
    DISEASES_PATH,
    GLIM_ACUTE_DISEASE_IDS,
    GLIM_CHRONIC_DISEASE_IDS,
    GLIM_GI_SYMPTOM_LABELS,
    GLIM_NUTRITION_IMPACT_LABELS,
)

# 疾病配置加载、缓存和查询函数集中在此模块。
diseases_cache: Dict[str, Any] = {"diseases": [], "nrs2002": {"diseases": []}, "glim": {}}


def normalize_diseases_config(data: Dict[str, Any]) -> Dict[str, Any]:
    legacy = data.get("diseases", [])
    if data.get("nrs2002") and data.get("glim"):
        return {
            "diseases": legacy,
            "nrs2002": data.get("nrs2002", {"diseases": legacy}),
            "glim": data.get("glim", {}),
        }
    return {
        "diseases": legacy,
        "nrs2002": {
            "diseases": [
                {"id": item["id"], "name": item["name"], "nrs_score": item.get("nrs_score", 0)}
                for item in legacy
            ]
        },
        "glim": {
            "intake_or_malabsorption": {
                "gi_symptoms": [{"id": key, "name": value} for key, value in GLIM_GI_SYMPTOM_LABELS.items()],
                "related_diseases": [{"id": key, "name": value} for key, value in GLIM_NUTRITION_IMPACT_LABELS.items()],
            },
            "inflammation_or_disease_burden": {
                "acute": [item for item in legacy if item.get("id") in GLIM_ACUTE_DISEASE_IDS],
                "chronic": [
                    item for item in legacy if item.get("id") in GLIM_CHRONIC_DISEASE_IDS
                ] + [{"id": "other", "name": "其他"}],
                "inflammatory_markers": [
                    {"id": "crp", "name": "CRP", "unit": "mg/L", "threshold": 5},
                    {"id": "il6", "name": "IL-6C", "unit": "pg/mL", "threshold": 7},
                ],
            },
        },
    }


def load_diseases_config() -> None:
    """服务启动时读取一次疾病配置，重启后可生效新增或删除。"""
    global diseases_cache
    with open(DISEASES_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    diseases_cache = normalize_diseases_config(data)


def option_map(items: List[Dict[str, Any]]) -> Dict[str, str]:
    return {item["id"]: item["name"] for item in items}


def get_disease_map() -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in diseases_cache.get("diseases", [])}


def get_nrs_disease_map() -> Dict[str, Dict[str, Any]]:
    items = diseases_cache.get("nrs2002", {}).get("diseases", [])
    return {item["id"]: item for item in items}


def get_glim_config() -> Dict[str, Any]:
    return diseases_cache.get("glim", {})


def get_glim_intake_config() -> Dict[str, Any]:
    return get_glim_config().get("intake_or_malabsorption", {})


def get_glim_inflammation_config() -> Dict[str, Any]:
    return get_glim_config().get("inflammation_or_disease_burden", {})
