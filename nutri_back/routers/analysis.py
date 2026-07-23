from typing import Dict

from fastapi import APIRouter, HTTPException
from services.draft_service import draft_500, read_draft_file
from services.qwen_analysis_service import generate_personalized_analysis

# 个性化建议始终读取服务端草稿，避免浏览器提交被篡改的评估结果。
router = APIRouter(deprecated=True)


@router.post("/analysis/personalized")
def personalized_analysis() -> Dict[str, object]:
    try:
        return generate_personalized_analysis(read_draft_file())
    except HTTPException:
        raise
    except Exception as exc:
        draft_500("生成个性化建议失败", exc)
