from typing import Dict

from fastapi import APIRouter

from schemas.assess_schemas import GLIMRequest, MNASFRequest, NRS2002Request
from services import assess_service, scale_document_service
from services.draft_service import save_assessment_result

# 临床营养评估量表接口路由。
router = APIRouter(deprecated=True)


@router.post("/assess/nrs2002")
def assess_nrs2002(payload: NRS2002Request) -> Dict[str, object]:
    result = assess_service.assess_nrs2002(payload)
    result["document_output"] = scale_document_service.generate_nrs_document(payload, result)
    save_assessment_result("nrs2002_result", result)
    return result


@router.post("/assess/mna_sf")
def assess_mna_sf(payload: MNASFRequest) -> Dict[str, object]:
    result = assess_service.assess_mna_sf(payload)
    result["document_output"] = scale_document_service.generate_mna_document(payload, result)
    save_assessment_result("mnasf_result", result)
    return result


@router.post("/assess/glim")
def assess_glim(payload: GLIMRequest) -> Dict[str, object]:
    result = assess_service.assess_glim(payload)
    result["document_output"] = scale_document_service.generate_glim_document(payload, result)
    save_assessment_result("glim_result", result)
    return result
