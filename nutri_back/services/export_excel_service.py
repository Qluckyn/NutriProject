"""Generate the shared export workbook from history snapshots; never persist patient rows in XLSX."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Sequence
from xml.etree import ElementTree as ET

from services import sga_service


EXPORT_TEMPLATE = Path(__file__).resolve().parents[1] / "scales" / "导出信息.xlsx"
SHEET_XML = "xl/worksheets/sheet1.xml"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"main": MAIN_NS}
ET.register_namespace("", MAIN_NS)


def _text_cell(column: str, row: int, value: Any) -> ET.Element:
    cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": f"{column}{row}", "s": "1", "t": "inlineStr"})
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
    text.text = "" if value is None else str(value)
    return cell


def _score(result: Any) -> str:
    return "" if not isinstance(result, dict) or result.get("total_score") is None else str(result["total_score"])


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


EXPORT_COLUMNS = tuple("ABCDEFGHIJKL")


def export_values(draft: Dict[str, Any], created_at: str) -> Dict[str, str]:
    patient = draft.get("patient_info") or {}
    glim = draft.get("glim_result") or {}
    image = draft.get("image_result") or {}
    evaluation = image.get("sga_evaluation") if isinstance(image, dict) else None
    if not isinstance(evaluation, dict):
        evaluation = sga_service.evaluate_sga(draft, image if isinstance(image, dict) else None)
    date = _date(created_at)
    glim_level = glim.get("severity") or ("未诊断营养不良" if glim else "")
    values = [
        str(patient.get("recordNumber") or ""), str(patient.get("name") or ""), str(patient.get("consultingDoctor") or ""),
        _score(draft.get("nrs2002_result")), _score(draft.get("mnasf_result")), date,
        "", "", str(evaluation.get("code") or "SGA评估信息不足"), date, str(glim_level), date,
    ]
    return dict(zip(EXPORT_COLUMNS, values))


def build_history_export(rows: Iterable[Sequence[str]]) -> bytes:
    """Render a fresh XLSX from history DB rows, preserving the template header and styles."""
    if not EXPORT_TEMPLATE.is_file():
        raise FileNotFoundError("导出信息.xlsx 模板不存在。")
    with zipfile.ZipFile(EXPORT_TEMPLATE, "r") as source:
        payloads = {info.filename: source.read(info.filename) for info in source.infolist()}
        infos = {info.filename: info for info in source.infolist()}
    root = ET.fromstring(payloads[SHEET_XML])
    sheet_data = root.find("main:sheetData", NS)
    if sheet_data is None:
        raise ValueError("导出信息.xlsx 缺少工作表数据。")
    for row in list(sheet_data.findall("main:row", NS)):
        if int(row.get("r", "0")) >= 3:
            sheet_data.remove(row)
    row_number = 2
    for record_id, created_at, snapshot, override_json, excluded in rows:
        if excluded:
            continue
        try:
            draft = snapshot if isinstance(snapshot, dict) else __import__("json").loads(snapshot)
            override = __import__("json").loads(override_json) if override_json else {}
        except (TypeError, ValueError):
            continue
        values = export_values(draft, created_at)
        if isinstance(override, dict):
            values.update({column: str(value or "") for column, value in override.items() if column in EXPORT_COLUMNS})
        row_number += 1
        row = ET.Element(f"{{{MAIN_NS}}}row", {"r": str(row_number), "spans": "1:12"})
        for column in EXPORT_COLUMNS:
            row.append(_text_cell(column, row_number, values[column]))
        sheet_data.append(row)
    dimension = root.find("main:dimension", NS)
    if dimension is not None:
        dimension.set("ref", f"A1:L{max(row_number, 2)}")
    payloads[SHEET_XML] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for filename, data in payloads.items():
            target.writestr(infos[filename], data)
    return output.getvalue()
