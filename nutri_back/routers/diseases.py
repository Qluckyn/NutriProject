from typing import Dict

from fastapi import APIRouter

from services import diseases_service

# 疾病配置查询接口路由。
router = APIRouter()


@router.get("/diseases")
def get_diseases() -> Dict[str, object]:
    return diseases_service.diseases_cache
