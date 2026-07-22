import base64
import binascii
import json
from pathlib import Path
from typing import Dict

from fastapi import HTTPException

from config import DRAFT_EXPLAIN_DIR, DRAFT_FILE, DRAFT_IMAGE_DIR, DRAFT_VIEWS

# 草稿 JSON、原始图片和可解释性图片的读写逻辑集中在此模块。
_EXPLAIN_IMAGE_KINDS = ("heatmap", "roi_overlay")


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
        "personalized_analysis": None,
    }


def init_draft_storage() -> None:
    """服务启动时确保草稿 JSON 和图片目录存在。"""
    try:
        Path(DRAFT_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
        Path(DRAFT_EXPLAIN_DIR).mkdir(parents=True, exist_ok=True)
        draft_path = Path(DRAFT_FILE)
        if not draft_path.exists():
            write_draft_file(default_draft_data())
    except Exception as exc:
        raise RuntimeError(f"初始化草稿存储失败：{exc}") from exc


def read_draft_file() -> Dict[str, object]:
    """以 utf-8 读取完整草稿，并迁移旧版 Base64 热力图。"""
    with open(DRAFT_FILE, "r", encoding="utf-8") as file:
        draft = json.load(file)
    if migrate_draft_explanation_images(draft):
        write_draft_file(draft)
    return draft


def write_draft_file(data: Dict[str, object]) -> None:
    """以 utf-8 覆盖写入完整草稿。可解释性图片只在文件系统保存。"""
    with open(DRAFT_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def ensure_draft_view(view: str) -> None:
    if view not in DRAFT_VIEWS:
        raise HTTPException(status_code=400, detail="图片视角只能是 front、left 或 right。")


def ensure_explain_kind(kind: str) -> None:
    if kind not in _EXPLAIN_IMAGE_KINDS:
        raise HTTPException(status_code=404, detail="可解释性图片不存在。")


def draft_image_path(view: str) -> Path:
    return Path(DRAFT_IMAGE_DIR) / f"{view}.jpg"


def draft_explain_image_path(view: str, kind: str) -> Path:
    ensure_draft_view(view)
    ensure_explain_kind(kind)
    return Path(DRAFT_EXPLAIN_DIR) / f"{view}_{kind}.png"


def _decode_data_url(value: object) -> bytes | None:
    if not isinstance(value, str) or not value.startswith("data:image/"):
        return None
    try:
        _, encoded = value.split(",", 1)
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None


def save_draft_explanation_images(result: Dict[str, object]) -> bool:
    """将 Base64 可解释性图保存为 PNG，并把结果对象替换为文件引用。"""
    views = result.get("views") if isinstance(result.get("views"), dict) else {}
    changed = False
    Path(DRAFT_EXPLAIN_DIR).mkdir(parents=True, exist_ok=True)

    for view, item in views.items():
        if view not in DRAFT_VIEWS or not isinstance(item, dict):
            continue
        for kind in _EXPLAIN_IMAGE_KINDS:
            base64_key = f"{kind}_base64"
            data = _decode_data_url(item.get(base64_key))
            if data is None:
                continue
            path = draft_explain_image_path(view, kind)
            path.write_bytes(data)
            item.pop(base64_key, None)
            item[f"{kind}_file"] = path.name
            changed = True
    return changed


def migrate_draft_explanation_images(draft: Dict[str, object]) -> bool:
    """把旧草稿中的 Base64 图片迁移为文件引用，保持刷新后的可解释性展示。"""
    result = draft.get("explain_result")
    return save_draft_explanation_images(result) if isinstance(result, dict) else False


def clear_draft_explanation_images() -> None:
    directory = Path(DRAFT_EXPLAIN_DIR)
    if not directory.exists():
        return
    for image_file in directory.iterdir():
        if image_file.is_file():
            image_file.unlink()


def save_assessment_result(result_key: str, result: Dict[str, object]) -> None:
    """Merge one completed assessment result into the existing draft."""
    draft = read_draft_file()
    draft[result_key] = result
    write_draft_file(draft)


def draft_500(message: str, exc: Exception) -> None:
    raise HTTPException(status_code=500, detail=f"{message}：{exc}") from exc
