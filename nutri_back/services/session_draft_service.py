import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from fastapi import HTTPException, Query

from config import DRAFT_VIEWS

_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_EXPLAIN_IMAGE_KINDS = ("heatmap", "roi_overlay")
_ROOT = Path(__file__).resolve().parents[1] / "sessions"


@dataclass(frozen=True)
class DraftScope:
    session_id: str
    assessment_id: str

    @property
    def root(self) -> Path:
        return _ROOT / self.session_id / self.assessment_id


def get_draft_scope(session_id: str = Query(...), assessment_id: str = Query(...)) -> DraftScope:
    if not _ID_RE.fullmatch(session_id) or not _ID_RE.fullmatch(assessment_id):
        raise HTTPException(400, "会话标识无效，请新建一次评估后重试。")
    return DraftScope(session_id, assessment_id)


def default_draft_data() -> Dict[str, object]:
    return {
        "patient_info": {}, "weight_records": {}, "intake_records": {},
        "nrs2002_form": {}, "mnasf_form": {}, "glim_form": {},
        "image_screening_form": {"giSymptoms": "none", "stressResponse": "no_fever", "ankleEdema": "none"},
        "images": {"front": None, "left": None, "right": None},
        "image_result": None, "explain_result": None, "nrs2002_result": None,
        "mnasf_result": None, "glim_result": None, "personalized_analysis": None,
    }


def init_session_storage() -> None:
    _ROOT.mkdir(parents=True, exist_ok=True)


def _ensure(scope: DraftScope) -> None:
    scope.root.mkdir(parents=True, exist_ok=True)
    (scope.root / "images").mkdir(exist_ok=True)
    (scope.root / "explain").mkdir(exist_ok=True)


def _file(scope: DraftScope) -> Path:
    return scope.root / "draft.json"


def read_draft(scope: DraftScope) -> Dict[str, object]:
    _ensure(scope)
    path = _file(scope)
    if not path.exists():
        write_draft(scope, default_draft_data())
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def write_draft(scope: DraftScope, data: Dict[str, object]) -> None:
    _ensure(scope)
    path = _file(scope)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
    temporary.replace(path)


def ensure_view(view: str) -> None:
    if view not in DRAFT_VIEWS:
        raise HTTPException(400, "图片视角只能是 front、left 或 right。")


def image_path(scope: DraftScope, view: str) -> Path:
    ensure_view(view)
    return scope.root / "images" / f"{view}.jpg"


def explain_path(scope: DraftScope, view: str, kind: str) -> Path:
    ensure_view(view)
    if kind not in _EXPLAIN_IMAGE_KINDS:
        raise HTTPException(404, "可解释性图片不存在。")
    return scope.root / "explain" / f"{view}_{kind}.png"


def clear_explanations(scope: DraftScope) -> None:
    folder = scope.root / "explain"
    if folder.exists():
        for item in folder.iterdir():
            if item.is_file():
                item.unlink()


def _decode(value: object) -> bytes | None:
    if not isinstance(value, str) or not value.startswith("data:image/"):
        return None
    try:
        return base64.b64decode(value.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error):
        return None


def save_explanations(scope: DraftScope, result: Dict[str, object]) -> bool:
    views = result.get("views") if isinstance(result.get("views"), dict) else {}
    changed = False
    _ensure(scope)
    for view, item in views.items():
        if view not in DRAFT_VIEWS or not isinstance(item, dict):
            continue
        for kind in _EXPLAIN_IMAGE_KINDS:
            data = _decode(item.get(f"{kind}_base64"))
            if data is None:
                continue
            path = explain_path(scope, view, kind)
            path.write_bytes(data)
            item.pop(f"{kind}_base64", None)
            item[f"{kind}_file"] = path.name
            changed = True
    return changed


def save_result(scope: DraftScope, key: str, result: Dict[str, object]) -> None:
    draft = read_draft(scope)
    draft[key] = result
    write_draft(scope, draft)

