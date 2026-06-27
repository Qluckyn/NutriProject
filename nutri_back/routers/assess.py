from typing import Dict

from fastapi import APIRouter

from schemas.assess_schemas import GLIMRequest, MNASFRequest, NRS2002Request
from services import assess_service

# 临床营养评估量表接口路由。
router = APIRouter()


@router.post("/assess/nrs2002")
def assess_nrs2002(payload: NRS2002Request) -> Dict[str, object]:
    return assess_service.assess_nrs2002(payload)


@router.post("/assess/mna_sf")
def assess_mna_sf(payload: MNASFRequest) -> Dict[str, object]:
    return assess_service.assess_mna_sf(payload)


@router.post("/assess/glim")
def assess_glim(payload: GLIMRequest) -> Dict[str, object]:
    return assess_service.assess_glim(payload)
