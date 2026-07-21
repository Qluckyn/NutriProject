import json
from pathlib import Path
from typing import Dict

from fastapi import HTTPException

from config import DRAFT_FILE, DRAFT_IMAGE_DIR, DRAFT_VIEWS

# 草稿JSON文件和草稿图片文件的读写逻辑集中在此模块。


def default_draft_data() -> Dict[str, object]:
    """返回草稿初始结构，供初始化和清空草稿复用。"""
    return {
        "patient_info": {},
        "weight_records": {},
        "intake_records": {},
        "nrs2002_form": {},
        "mnasf_form": {},
        "glim_form": {},
        "image_screening_form": {"giSymptoms": "none", "stressResponse": "no_fever", "ankleEdema": "none"},
        "images": {"front": None, "left": None, "right": None},
        "image_result": None,
        "explain_result": None,
        "nrs2002_result": None,
        "mnasf_result": None,
        "glim_result": None,
    }


def init_draft_storage() -> None:
    """服务启动时确保草稿JSON和图片目录存在。"""
    try:
        image_dir = Path(DRAFT_IMAGE_DIR)
        image_dir.mkdir(parents=True, exist_ok=True)
        draft_path = Path(DRAFT_FILE)
        if not draft_path.exists():
            write_draft_file(default_draft_data())
    except Exception as exc:
        raise RuntimeError(f"初始化草稿存储失败：{exc}") from exc


def read_draft_file() -> Dict[str, object]:
    """以utf-8读取完整草稿文件。"""
    with open(DRAFT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def write_draft_file(data: Dict[str, object]) -> None:
    """以utf-8覆盖写入完整草稿文件。"""
    with open(DRAFT_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def ensure_draft_view(view: str) -> None:
    if view not in DRAFT_VIEWS:
        raise HTTPException(status_code=400, detail="图片视角只能是 front、left 或 right。")


def draft_image_path(view: str) -> Path:
    return Path(DRAFT_IMAGE_DIR) / f"{view}.jpg"


def draft_500(message: str, exc: Exception) -> None:
    raise HTTPException(status_code=500, detail=f"{message}：{exc}") from exc
