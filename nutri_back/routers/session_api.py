import io
import json
import shutil
import sqlite3
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image

from config import DRAFT_VIEWS
from model_loader import aggregate_scores, build_message, predict_one_view, round4, validate_image_file
from routers import assess as assess_router
from schemas.assess_schemas import GLIMRequest, MNASFRequest, NRS2002Request
from services import assess_service, scale_document_service
from services.draft_service import draft_500
from services.explain_service import TARGET_CLASS_NOTE, explain_single_view
from services.qwen_analysis_service import generate_personalized_analysis
from services.session_draft_service import (
    DraftScope, clear_explanations, default_draft_data, explain_path, get_draft_scope,
    image_path, read_draft, save_explanations, save_result, write_draft,
)

router = APIRouter()
BASE = Path(__file__).resolve().parents[1]
DB = BASE / "history.db"
ARCHIVES = BASE / "history_reports"
RESULT_KEYS = ("nrs2002_result", "mnasf_result", "image_result", "glim_result")
REPORT_KEYS = {"nrs2002": "nrs2002_result", "mnasf": "mnasf_result", "image": "image_result", "glim": "glim_result"}


def _history_db() -> sqlite3.Connection:
    ARCHIVES.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, patient_name TEXT NOT NULL, snapshot TEXT NOT NULL, advice TEXT)")
    columns = {row[1] for row in con.execute("PRAGMA table_info(history)")}
    if "folder_name" not in columns:
        con.execute("ALTER TABLE history ADD COLUMN folder_name TEXT")
        con.execute("UPDATE history SET folder_name = id WHERE folder_name IS NULL OR trim(folder_name) = ''")
    if "session_id" not in columns:
        con.execute("ALTER TABLE history ADD COLUMN session_id TEXT")
    return con


def _history_row(scope: DraftScope, record_id: str):
    with _history_db() as con:
        row = con.execute("SELECT id, created_at, patient_name, snapshot, advice, folder_name FROM history WHERE id = ?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, "历史记录不存在。")
    return row


@router.get("/draft")
def get_draft(scope: DraftScope = Depends(get_draft_scope)):
    return read_draft(scope)


@router.post("/draft")
def save_draft(data: Dict[str, object], scope: DraftScope = Depends(get_draft_scope)):
    try:
        if isinstance(data.get("explain_result"), dict):
            save_explanations(scope, data["explain_result"])
        else:
            clear_explanations(scope)
        write_draft(scope, data)
        return {"saved": True}
    except Exception as exc:
        draft_500("保存草稿失败", exc)


@router.delete("/draft")
def clear_draft(scope: DraftScope = Depends(get_draft_scope)):
    try:
        for view in DRAFT_VIEWS:
            path = image_path(scope, view)
            if path.exists():
                path.unlink()
        clear_explanations(scope)
        data = default_draft_data()
        write_draft(scope, data)
        return data
    except Exception as exc:
        draft_500("清空草稿失败", exc)


@router.post("/draft/image/{view}")
async def save_image(view: str, file: UploadFile = File(...), scope: DraftScope = Depends(get_draft_scope)):
    try:
        validate_image_file(file, view)
        image = Image.open(io.BytesIO(await file.read())).convert("RGB")
        path = image_path(scope, view)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="JPEG", quality=90, optimize=True)
        draft = read_draft(scope)
        images = draft.get("images") or {}
        images[view] = {"filename": file.filename, "saved": True}
        draft["images"] = images
        write_draft(scope, draft)
        return {"saved": True, "view": view, "filename": file.filename}
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("保存草稿图片失败", exc)


@router.get("/draft/image/{view}")
def get_image(view: str, scope: DraftScope = Depends(get_draft_scope)):
    path = image_path(scope, view)
    if not path.exists():
        raise HTTPException(404, "草稿图片不存在。")
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/draft/image/{view}")
def delete_image(view: str, scope: DraftScope = Depends(get_draft_scope)):
    path = image_path(scope, view)
    if path.exists():
        path.unlink()
    draft = read_draft(scope)
    images = draft.get("images") or {}
    images[view] = None
    draft["images"] = images
    write_draft(scope, draft)
    return {"deleted": True, "view": view}


@router.get("/draft/explain/{view}/{kind}")
def get_explanation(view: str, kind: str, scope: DraftScope = Depends(get_draft_scope)):
    path = explain_path(scope, view, kind)
    if not path.exists():
        raise HTTPException(404, "可解释性图片不存在。")
    return FileResponse(path, media_type="image/png")


@router.post("/predict/draft")
def predict_draft(scope: DraftScope = Depends(get_draft_scope)):
    try:
        draft, scores, used = read_draft(scope), {}, []
        for view in DRAFT_VIEWS:
            info, path = (draft.get("images") or {}).get(view), image_path(scope, view)
            if info and info.get("saved") and path.exists():
                scores[view] = predict_one_view(Image.open(path).convert("RGB"))
                used.append(view)
        if not used:
            raise HTTPException(400, "请至少先上传并保存一张面部图片。")
        prediction, mal, normal = aggregate_scores(scores)
        result = {"prediction": prediction, "malnourished_probability": round4(mal), "normal_probability": round4(normal), "confidence": round4(max(mal, normal)), "sga_normalized_score": round4(mal * 7), "n_views_used": len(used), "views_used": used, "per_view_scores": scores, "message": build_message(prediction, mal, used)}
        result["document_output"] = scale_document_service.generate_sga_document(draft, result)
        save_result(scope, "image_result", result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("草稿图片筛查失败", exc)


@router.post("/explain/roi/draft")
def explain_draft(scope: DraftScope = Depends(get_draft_scope)):
    try:
        draft, views = read_draft(scope), {}
        for view in DRAFT_VIEWS:
            info, path = (draft.get("images") or {}).get(view), image_path(scope, view)
            if info and info.get("saved") and path.exists():
                views[view] = explain_single_view(Image.open(path).convert("RGB"), view)
        if not views:
            raise HTTPException(400, "请至少先上传并保存一张面部图片。")
        result = {"target_class_note": TARGET_CLASS_NOTE, "views": views}
        save_explanations(scope, result)
        save_result(scope, "explain_result", result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("草稿图片可解释性分析失败", exc)


def _assess(payload, key, generator, assessor, scope):
    result = assessor(payload)
    result["document_output"] = generator(payload, result)
    save_result(scope, key, result)
    return result


@router.post("/assess/nrs2002")
def nrs(payload: NRS2002Request, scope: DraftScope = Depends(get_draft_scope)):
    return _assess(payload, "nrs2002_result", scale_document_service.generate_nrs_document, assess_service.assess_nrs2002, scope)


@router.post("/assess/mna_sf")
def mna(payload: MNASFRequest, scope: DraftScope = Depends(get_draft_scope)):
    return _assess(payload, "mnasf_result", scale_document_service.generate_mna_document, assess_service.assess_mna_sf, scope)


@router.post("/assess/glim")
def glim(payload: GLIMRequest, scope: DraftScope = Depends(get_draft_scope)):
    return _assess(payload, "glim_result", scale_document_service.generate_glim_document, assess_service.assess_glim, scope)


@router.get("/reports/file/{report_key}")
def report_file(report_key: str, scope: DraftScope = Depends(get_draft_scope)):
    key = REPORT_KEYS.get(report_key)
    output = (read_draft(scope).get(key) or {}).get("document_output") if key else None
    path = Path(output).resolve() if output else None
    if not path or scale_document_service.OUTPUT_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "该评估尚未生成可下载报告。")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)


@router.post("/analysis/personalized")
def personalized(scope: DraftScope = Depends(get_draft_scope)):
    return generate_personalized_analysis(read_draft(scope))


@router.post("/history")
def save_history(payload: Dict[str, object], scope: DraftScope = Depends(get_draft_scope)):
    draft = read_draft(scope)
    if not draft.get("nrs2002_result") or not draft.get("glim_result") or (not draft.get("image_result") and not draft.get("skipped_image")):
        raise HTTPException(422, "请先完成 NRS-2002、GLIM 评估，并完成或跳过面部图像筛查。")
    record_id, now = uuid.uuid4().hex, datetime.now()
    folder_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{record_id[:8]}"
    folder, reports, images = ARCHIVES / folder_name, ARCHIVES / folder_name / "reports", ARCHIVES / folder_name / "images"
    reports.mkdir(parents=True)
    images.mkdir(parents=True)
    snapshot = json.loads(json.dumps(draft, ensure_ascii=False))
    snapshot.pop("explain_result", None)
    for key in RESULT_KEYS:
        source = Path((snapshot.get(key) or {}).get("document_output", ""))
        if source.is_file():
            shutil.copy2(source, reports / source.name)
            snapshot[key]["history_report"] = source.name
    for view in DRAFT_VIEWS:
        source = image_path(scope, view)
        if source.is_file():
            shutil.copy2(source, images / f"{view}.jpg")
            snapshot.setdefault("images", {}).setdefault(view, {})["history_image"] = f"{view}.jpg"
    with _history_db() as con:
        con.execute("INSERT INTO history (id, created_at, patient_name, snapshot, advice, folder_name, session_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (record_id, now.strftime("%Y-%m-%d %H:%M:%S"), str((draft.get("patient_info") or {}).get("name") or "未命名患者"), json.dumps(snapshot, ensure_ascii=False), json.dumps(payload.get("personalized_analysis"), ensure_ascii=False) if payload.get("personalized_analysis") else None, folder_name, scope.session_id))
    return {"id": record_id, "created_at": now.strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/history")
def list_history(scope: DraftScope = Depends(get_draft_scope)):
    with _history_db() as con:
        rows = con.execute("SELECT id, created_at, patient_name FROM history ORDER BY created_at DESC").fetchall()
    return [{"id": row[0], "created_at": row[1], "patient_name": row[2]} for row in rows]


@router.get("/history/{record_id}")
def history_detail(record_id: str, scope: DraftScope = Depends(get_draft_scope)):
    row = _history_row(scope, record_id)
    return {"id": row[0], "created_at": row[1], "patient_name": row[2], "snapshot": json.loads(row[3]), "personalized_analysis": json.loads(row[4]) if row[4] else None}


@router.delete("/history/{record_id}")
def delete_history(record_id: str, scope: DraftScope = Depends(get_draft_scope)):
    row = _history_row(scope, record_id)
    folder = (ARCHIVES / row[5]).resolve()
    if ARCHIVES.resolve() not in folder.parents:
        raise HTTPException(404, "历史记录不存在。")
    with _history_db() as con:
        con.execute("DELETE FROM history WHERE id = ?", (record_id,))
    shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": True}


@router.get("/history/{record_id}/reports.zip")
def history_reports_archive(record_id: str, scope: DraftScope = Depends(get_draft_scope)):
    row = _history_row(scope, record_id)
    folder = (ARCHIVES / row[5]).resolve()
    report_folder = (folder / "reports").resolve()
    if ARCHIVES.resolve() not in folder.parents or folder not in report_folder.parents or not report_folder.is_dir():
        raise HTTPException(404, "历史报告不存在。")
    reports = sorted(path for path in report_folder.iterdir() if path.is_file() and path.suffix.lower() == ".docx")
    if not reports:
        raise HTTPException(404, "历史报告不存在。")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in reports:
            bundle.write(path, arcname=path.name)
    patient_name = str(row[2] or "未命名患者").strip()
    safe_name = "".join("_" if char in ("\\", "/", ":", "*", "?", "\"", "<", ">", "|") else char for char in patient_name).strip() or "未命名患者"
    try:
        timestamp = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")
    except (TypeError, ValueError):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{safe_name}_全部量表.zip"
    return Response(archive.getvalue(), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}", "Cache-Control": "no-store"})


def _history_file(scope: DraftScope, record_id: str, relative: Path) -> Path:
    row = _history_row(scope, record_id)
    folder = (ARCHIVES / row[5]).resolve()
    path = (folder / relative).resolve()
    if folder not in path.parents or not path.is_file():
        raise HTTPException(404, "历史文件不存在。")
    return path


@router.get("/history/{record_id}/reports/{filename}")
def history_report(record_id: str, filename: str, scope: DraftScope = Depends(get_draft_scope)):
    path = _history_file(scope, record_id, Path("reports") / filename)
    if path.suffix.lower() != ".docx":
        raise HTTPException(404, "历史报告不存在。")
    return FileResponse(path, filename=path.name)


@router.get("/history/{record_id}/images/{view}")
def history_image(record_id: str, view: str, scope: DraftScope = Depends(get_draft_scope)):
    if view not in DRAFT_VIEWS:
        raise HTTPException(404, "历史图片不存在。")
    path = _history_file(scope, record_id, Path("images") / f"{view}.jpg")
    return FileResponse(path, media_type="image/jpeg")



@router.get("/reports/archive")
def download_current_reports_archive(scope: DraftScope = Depends(get_draft_scope)) -> Response:
    """将当前会话中已生成的 DOCX 报告打包为单个 ZIP 下载。"""
    draft = read_draft(scope)
    report_keys = (
        ("nrs2002_result", "nrs2002"),
        ("mnasf_result", "mnasf"),
        ("image_result", "image"),
        ("glim_result", "glim"),
    )
    archive = io.BytesIO()
    included = 0
    output_dir = scale_document_service.OUTPUT_DIR.resolve()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for result_key, report_key in report_keys:
            if report_key == "mnasf" and draft.get("skipped_mnasf"):
                continue
            result = draft.get(result_key) or {}
            document_output = result.get("document_output") if isinstance(result, dict) else None
            if not document_output:
                continue
            path = Path(document_output).resolve()
            if output_dir not in path.parents or path.suffix.lower() != ".docx" or not path.is_file():
                raise HTTPException(404, "报告文件不存在，请重新完成该项评估。")
            bundle.write(path, arcname=path.name)
            included += 1
    if not included:
        raise HTTPException(404, "暂无可下载的评估报告。")
    patient_name = str((draft.get("patient_info") or {}).get("name") or "未命名患者").strip()
    safe_name = "".join("_" if char in ("\\", "/", ":", "*", "?", "\"", "<", ">", "|") else char for char in patient_name).strip() or "未命名患者"
    filename = f"{datetime.now():%Y%m%d_%H%M%S}_{safe_name}_全部量表.zip"
    return Response(
        archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )
