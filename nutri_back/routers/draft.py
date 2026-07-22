import io
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from config import DRAFT_IMAGE_DIR
from model_loader import validate_image_file
from services.draft_service import (
    clear_draft_explanation_images,
    default_draft_data,
    draft_explain_image_path,
    draft_500,
    draft_image_path,
    ensure_draft_view,
    read_draft_file,
    save_draft_explanation_images,
    write_draft_file,
)

# 草稿JSON和草稿图片持久化接口路由。
router = APIRouter()


@router.get("/draft")
def get_draft() -> Dict[str, object]:
    """读取并返回完整草稿。"""
    try:
        return read_draft_file()
    except Exception as exc:
        draft_500("读取草稿失败", exc)


@router.post("/draft")
def save_draft(data: Dict[str, object]) -> Dict[str, object]:
    """接收前端完整草稿并覆盖保存。"""
    try:
        if isinstance(data.get("explain_result"), dict):
            save_draft_explanation_images(data["explain_result"])
        write_draft_file(data)
        if not data.get("explain_result"):
            clear_draft_explanation_images()
        return {"saved": True}
    except Exception as exc:
        draft_500("保存草稿失败", exc)


@router.delete("/draft")
def clear_draft() -> Dict[str, object]:
    """重置草稿JSON，并清空草稿图片目录。"""
    try:
        image_dir = Path(DRAFT_IMAGE_DIR)
        image_dir.mkdir(parents=True, exist_ok=True)
        for image_file in image_dir.iterdir():
            if image_file.is_file():
                image_file.unlink()
        clear_draft_explanation_images()
        initial_data = default_draft_data()
        write_draft_file(initial_data)
        return initial_data
    except Exception as exc:
        draft_500("清空草稿失败", exc)


@router.post("/draft/image/{view}")
async def save_draft_image(view: str, file: UploadFile = File(...)) -> Dict[str, object]:
    """保存单个视角草稿图片，并更新草稿JSON中的图片状态。"""
    try:
        ensure_draft_view(view)
        validate_image_file(file, view)
        content = await file.read()
        # 后端只统一为RGB三通道并保存，真正的Resize/CenterCrop仍由模型transform完成。
        image = Image.open(io.BytesIO(content)).convert("RGB")
        Path(DRAFT_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
        image.save(draft_image_path(view), format="JPEG", quality=90, optimize=True)

        draft = read_draft_file()
        images = draft.get("images") or {"front": None, "left": None, "right": None}
        images[view] = {"filename": file.filename, "saved": True}
        draft["images"] = images
        write_draft_file(draft)
        return {"saved": True, "view": view, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("保存草稿图片失败", exc)


@router.get("/draft/image/{view}")
def get_draft_image(view: str) -> FileResponse:
    """直接返回指定视角的草稿图片文件。"""
    try:
        ensure_draft_view(view)
        image_path = draft_image_path(view)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="草稿图片不存在。")
        return FileResponse(str(image_path), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("读取草稿图片失败", exc)


@router.get("/draft/explain/{view}/{kind}")
def get_draft_explanation_image(view: str, kind: str) -> FileResponse:
    """返回草稿中保存的可解释性 PNG。"""
    try:
        path = draft_explain_image_path(view, kind)
        if not path.exists():
            raise HTTPException(status_code=404, detail="可解释性图片不存在。")
        return FileResponse(str(path), media_type="image/png")
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("读取可解释性图片失败", exc)


@router.delete("/draft/image/{view}")
def delete_draft_image(view: str) -> Dict[str, object]:
    """删除指定视角草稿图片，并将草稿JSON中的图片状态置空。"""
    try:
        ensure_draft_view(view)
        image_path = draft_image_path(view)
        if image_path.exists():
            image_path.unlink()

        draft = read_draft_file()
        images = draft.get("images") or {"front": None, "left": None, "right": None}
        images[view] = None
        draft["images"] = images
        write_draft_file(draft)
        return {"deleted": True, "view": view}
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("删除草稿图片失败", exc)
