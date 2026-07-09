from typing import Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from model_loader import read_image
from services.draft_service import draft_500, draft_image_path, read_draft_file
from services.explain_service import TARGET_CLASS_NOTE, explain_single_view

router = APIRouter()


def _build_response(views: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    return {"target_class_note": TARGET_CLASS_NOTE, "views": views}


@router.post("/explain/roi")
async def explain_roi(
    front: Optional[UploadFile] = File(None),
    left: Optional[UploadFile] = File(None),
    right: Optional[UploadFile] = File(None),
) -> Dict[str, object]:
    uploads = {"front": front, "left": left, "right": right}
    available_uploads = {name: file for name, file in uploads.items() if file is not None}

    if not available_uploads:
        raise HTTPException(status_code=400, detail="请至少上传一张面部图片。")

    views: Dict[str, Dict[str, object]] = {}
    for view_name, upload in available_uploads.items():
        image = await read_image(upload, view_name)
        views[view_name] = explain_single_view(image, view_name)
    return _build_response(views)


@router.post("/explain/roi/draft")
def explain_roi_from_draft_images() -> Dict[str, object]:
    try:
        draft = read_draft_file()
        images = draft.get("images") or {}
        views: Dict[str, Dict[str, object]] = {}

        for view_name in ("front", "left", "right"):
            image_info = images.get(view_name)
            image_path = draft_image_path(view_name)
            if not image_info or not image_info.get("saved") or not image_path.exists():
                continue
            image = Image.open(image_path).convert("RGB")
            views[view_name] = explain_single_view(image, view_name)

        if not views:
            raise HTTPException(status_code=400, detail="请至少先上传并保存一张面部图片。")
        return _build_response(views)
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("草稿图片可解释性分析失败", exc)
