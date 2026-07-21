from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# 临床营养评估量表请求体模型集中在此模块。


class NRS2002Request(BaseModel):
    patient_name: str = Field("")
    gender: str = Field("")
    age: int = Field(..., ge=0, le=110)
    height: float = Field(..., ge=100, le=250)
    weight_records: Dict[str, float] = Field(...)
    intake_last_week: float = Field(..., ge=0, le=100)
    disease_ids: List[str] = Field(default_factory=list)
    general_condition_impaired: bool = Field(...)


class MNASFRequest(BaseModel):
    patient_name: str = Field("")
    gender: str = Field("")
    age: int = Field(..., ge=0, le=110)
    height: float = Field(..., ge=100, le=250)
    weight_records: Dict[str, float] = Field(...)
    intake_last_week: float = Field(..., ge=0, le=100)
    mobility: int = Field(..., ge=0, le=2)
    stress_or_acute_disease: bool = Field(...)
    mental_status: int = Field(..., ge=0, le=2)
    use_bmi: bool = Field(...)
    calf_circumference: Optional[float] = Field(None, gt=0)


class GLIMRequest(BaseModel):
    patient_name: str = Field("")
    gender: str = Field("")
    age: int = Field(..., ge=0, le=110)
    height: float = Field(..., ge=100, le=250)
    weight_records: Dict[str, float] = Field(...)
    muscle_loss: str = Field(...)
    # 兼容旧请求；严格判定优先使用下面与图片表单一致的细项字段。
    disease_ids: List[str] = Field(default_factory=list)
    reduced_intake: bool = Field(False)
    intake_under_50_over_1w: bool = Field(False)
    any_intake_reduction_over_2w: bool = Field(False)
    gi_symptoms: List[str] = Field(default_factory=list)
    nutrition_impact_conditions: List[str] = Field(default_factory=list)
    acute_disease_ids: List[str] = Field(default_factory=list)
    chronic_disease_ids: List[str] = Field(default_factory=list)
    cancer_site: str = Field("")
    cancer_stage: str = Field("")
    cancer_malnutrition_related: Optional[bool] = Field(None)
    crp: Optional[float] = Field(None, ge=0)
    il6: Optional[float] = Field(None, ge=0)
