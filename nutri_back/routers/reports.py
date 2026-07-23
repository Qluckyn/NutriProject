from io import BytesIO
from pathlib import Path
import zipfile
from typing import Dict, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from services.draft_service import read_draft_file
from services.scale_document_service import OUTPUT_DIR

# 下载只允许读取本次草稿中已生成的四类量表文件，防止任意路径读取。
router = APIRouter()
_REPORTS: Dict[str, Tuple[str, str]] = {
    "nrs2002": ("nrs2002_result", "NRS-2002 营养风险筛查"),
    "mnasf": ("mnasf_result", "MNA-SF 微型营养评估"),
    "image": ("image_result", "SGA 面部图像筛查"),
    "glim": ("glim_result", "GLIM 营养不良评定"),
}


def _report_path(report_key: str) -> Path:
    """从草稿结果取得已生成文档，并确认它位于受控的输出目录。"""
    if report_key not in _REPORTS:
        raise HTTPException(status_code=404, detail="未找到该报告类型。")
    result_key, _ = _REPORTS[report_key]
    result = read_draft_file().get(result_key) or {}
    document_output = result.get("document_output") if isinstance(result, dict) else None
    if not document_output:
        raise HTTPException(status_code=404, detail="该评估尚未生成可下载报告。")
    output_path = Path(document_output).resolve()
    output_dir = OUTPUT_DIR.resolve()
    if output_dir not in output_path.parents or output_path.suffix.lower() != ".docx" or not output_path.is_file():
        raise HTTPException(status_code=404, detail="报告文件不存在，请重新完成该项评估。")
    return output_path


@router.get("/reports/file/{report_key}")
def download_report(report_key: str) -> FileResponse:
    """下载单个已生成的 DOCX 报告。"""
    report_path = _report_path(report_key)
    return FileResponse(report_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=report_path.name)



@router.get("/reports/archive")
def download_reports_archive() -> Response:
    """将当前草稿中全部已生成的 DOCX 报告打包为单个 ZIP 下载。"""
    draft = read_draft_file()
    report_keys = [key for key, (result_key, _) in _REPORTS.items() if (draft.get(result_key) or {}).get("document_output")]
    if draft.get("skipped_mnasf"):
        report_keys = [key for key in report_keys if key != "mnasf"]
    if not report_keys:
        raise HTTPException(status_code=404, detail="暂无可下载的评估报告。")

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for report_key in report_keys:
            path = _report_path(report_key)
            bundle.write(path, arcname=path.name)
    return Response(
        archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=assessment_reports.zip",
            "Cache-Control": "no-store",
        },
    )
