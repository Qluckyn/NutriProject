import io
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from torchvision import transforms

# 将训练代码目录加入导入路径，保证模型结构与训练阶段一致。
sys.path.insert(0, "./classify_model")
from models.clip import CLIP as NutriCLIP  # noqa: E402


# =========================
# 集中配置
# =========================
# YHQ的
CHECKPOINT_PATH = "./classify_model/weight/best_checkpoint.pth"
# SZJ的
# CHECKPOINT_PATH = "./classify_model/weight2/best_checkpoint.pth"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CLASS_NAMES = ["malnourished_face", "normal_face"]
POSITIVE_CLASS = "malnourished_face"
POS_IDX = CLASS_NAMES.index(POSITIVE_CLASS)
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
VIEW_LABELS = {
    "front": "正面",
    "left": "左45°",
    "right": "右45°",
}

# 图像预处理必须与训练阶段保持一致。
transform = transforms.Compose(
    [
        transforms.Resize(224, interpolation=Image.BICUBIC),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=(0.48145466, 0.4578275, 0.40821073),
            std=(0.26862954, 0.26130258, 0.27577711),
        ),
    ]
)

app = FastAPI(
    title="营养状态筛查系统 API",
    description="基于面部图像的老年营养不良辅助筛查后端服务",
    version="1.0.0",
)

# 开发阶段允许全部来源跨域访问，便于前后端分离联调。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model: Optional[NutriCLIP] = None


def round4(value: float) -> float:
    """统一保留4位小数，保证接口返回稳定。"""
    return round(float(value), 4)


def validate_image_file(file: UploadFile, view_name: str) -> None:
    """检查上传文件扩展名，避免非图片文件进入推理流程。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"{VIEW_LABELS[view_name]}图片格式不支持，请上传 jpg、jpeg、png 或 bmp 文件。",
        )


async def read_image(file: UploadFile, view_name: str) -> Image.Image:
    """读取上传图片并转为RGB，保证进入模型的是三通道图像。"""
    validate_image_file(file, view_name)
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        return image
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{VIEW_LABELS[view_name]}图片无法识别，请重新上传清晰图片。",
        ) from exc


def preprocess_image(image: Image.Image) -> torch.Tensor:
    """按训练配置预处理，并在推理时转为float16。"""
    tensor = transform(image).unsqueeze(0).to(DEVICE)
    # tensor = tensor.to(torch.float16)
    return tensor


def ensure_model_loaded() -> NutriCLIP:
    """在推理前确认模型已经加载完成。"""
    if model is None:
        raise HTTPException(status_code=503, detail="模型尚未加载完成，请稍后重试。")
    return model


def predict_one_view(image: Image.Image) -> Dict[str, float]:
    """单视角推理，返回两个类别的概率。"""
    current_model = ensure_model_loaded()
    image_tensor = preprocess_image(image)

    with torch.no_grad():
        output = current_model(image_tensor)
        probs = F.softmax(output, dim=1)[0].detach().float().cpu()

    return {
        CLASS_NAMES[0]: round4(probs[0].item()),
        CLASS_NAMES[1]: round4(probs[1].item()),
    }


def build_message(prediction: str, probability: float, views_used: List[str]) -> str:
    """根据聚合结果生成面向用户的中文说明。"""
    view_text = "、".join(VIEW_LABELS[item] for item in views_used)
    percent = f"{probability * 100:.2f}%"
    if prediction == "malnourished":
        return (
            f"系统基于{view_text}图像分析，营养不良风险概率为{percent}。"
            "该结果仅用于辅助筛查，建议结合量表、体重变化、饮食摄入和临床评估进一步确认。"
        )
    return (
        f"系统基于{view_text}图像分析，当前更倾向于营养状态正常，营养不良风险概率为{percent}。"
        "如近期存在体重下降、食欲减退或基础疾病变化，仍建议进行专业营养评估。"
    )


def aggregate_scores(per_view_scores: Dict[str, Dict[str, float]]) -> Tuple[str, float, float]:
    """subject级别聚合：多张图片的营养不良概率取平均。"""
    mal_scores = [scores[POSITIVE_CLASS] for scores in per_view_scores.values()]
    avg_mal_score = sum(mal_scores) / len(mal_scores)
    normal_score = 1.0 - avg_mal_score
    prediction = "malnourished" if avg_mal_score >= 0.5 else "normal"
    return prediction, avg_mal_score, normal_score


@app.on_event("startup")
def load_model() -> None:
    """服务启动时加载一次模型权重，后续请求复用同一个模型实例。"""
    global model
    current_model = NutriCLIP(
        dataset="my_dataset",
        is_lora_image=True,
        is_lora_text=True,
        clip_download_dir=None,
        clip_version="ViT-B/16",
    )
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=False)
    current_model.load_state_dict(checkpoint["model"], strict=False)
    model = current_model.to(DEVICE).eval()


@app.get("/health")
def health() -> Dict[str, object]:
    return {"status": "ok", "model_loaded": model is not None, "device": DEVICE}


@app.get("/info")
def info() -> Dict[str, object]:
    return {
        "model_name": "NutriCLIP",
        "dataset": "my_dataset",
        "clip_version": "ViT-B/16",
        "checkpoint_path": CHECKPOINT_PATH,
        "device": DEVICE,
        "classes": CLASS_NAMES,
        "positive_class": POSITIVE_CLASS,
        "supported_image_formats": sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS),
        "aggregation": "多视角营养不良概率取平均，阈值0.5判定为营养不良",
    }


@app.post("/predict")
async def predict(
    front: Optional[UploadFile] = File(None),
    left: Optional[UploadFile] = File(None),
    right: Optional[UploadFile] = File(None),
) -> Dict[str, object]:
    uploads = {"front": front, "left": left, "right": right}
    available_uploads = {name: file for name, file in uploads.items() if file is not None}

    if not available_uploads:
        raise HTTPException(status_code=400, detail="请至少上传一张面部图片。")

    per_view_scores: Dict[str, Dict[str, float]] = {}
    views_used: List[str] = []

    for view_name, upload in available_uploads.items():
        image = await read_image(upload, view_name)
        per_view_scores[view_name] = predict_one_view(image)
        views_used.append(view_name)

    prediction, mal_prob, normal_prob = aggregate_scores(per_view_scores)
    confidence = max(mal_prob, normal_prob)

    return {
        "prediction": prediction,
        "malnourished_probability": round4(mal_prob),
        "normal_probability": round4(normal_prob),
        "confidence": round4(confidence),
        "n_views_used": len(views_used),
        "views_used": views_used,
        "per_view_scores": per_view_scores,
        "message": build_message(prediction, mal_prob, views_used),
    }


# =========================
# 临床营养评估量表接口（追加）
# =========================
import json
from typing import Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

DISEASES_PATH = "./diseases.json"
REQUIRED_NRS_MONTHS = ("0", "1", "2", "3")
REQUIRED_GLIM_MONTHS = ("0", "6", "12")

diseases_cache: Dict[str, List[Dict[str, Any]]] = {"diseases": []}


class NRS2002Request(BaseModel):
    age: int = Field(..., ge=0, le=130)
    height: float = Field(..., gt=0)
    weight_records: Dict[str, float] = Field(...)
    intake_last_week: float = Field(..., ge=0, le=100)
    disease_ids: List[str] = Field(default_factory=list)
    general_condition_impaired: bool = Field(...)


class MNASFRequest(BaseModel):
    age: int = Field(..., ge=0, le=130)
    height: float = Field(..., gt=0)
    weight_records: Dict[str, float] = Field(...)
    intake_last_week: float = Field(..., ge=0, le=100)
    mobility: int = Field(..., ge=0, le=2)
    stress_or_acute_disease: bool = Field(...)
    mental_status: int = Field(..., ge=0, le=2)
    use_bmi: bool = Field(...)
    calf_circumference: Optional[float] = Field(None, gt=0)


class GLIMRequest(BaseModel):
    age: int = Field(..., ge=0, le=130)
    height: float = Field(..., gt=0)
    weight_records: Dict[str, float] = Field(...)
    muscle_loss: str = Field(...)
    disease_ids: List[str] = Field(default_factory=list)
    reduced_intake: bool = Field(...)
    crp: float = Field(-1)
    il6: float = Field(-1)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """将FastAPI默认422错误转成中文说明，便于前端直接展示。"""
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(item) for item in err.get("loc", []) if item != "body")
        errors.append(f"{loc or '请求体'}：{err.get('msg', '参数不合法')}")
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数缺失或格式不正确。" + "；".join(errors)},
    )


@app.on_event("startup")
def load_diseases_config() -> None:
    """服务启动时读取一次疾病配置，重启后可生效新增或删除。"""
    global diseases_cache
    with open(DISEASES_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    diseases_cache = {"diseases": data.get("diseases", [])}


def get_disease_map() -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in diseases_cache.get("diseases", [])}


def raise_zh_422(message: str) -> None:
    raise HTTPException(status_code=422, detail=message)


def validate_weight_records(records: Dict[str, float], required_months: Tuple[str, ...]) -> None:
    """校验必填月份体重，避免除零和缺失字段影响评分。"""
    missing = [month for month in required_months if month not in records or records[month] is None]
    if missing:
        raise_zh_422("缺少必填体重记录：" + "、".join(f"距今{month}个月" for month in missing))
    invalid = [month for month, value in records.items() if value is None or float(value) <= 0]
    if invalid:
        raise_zh_422("体重必须为大于0的数字：" + "、".join(f"距今{month}个月" for month in invalid))


def validate_disease_ids(disease_ids: List[str]) -> None:
    disease_map = get_disease_map()
    unknown = [item for item in disease_ids if item not in disease_map]
    if unknown:
        raise_zh_422("疾病id不存在：" + "、".join(unknown))


def calc_bmi(weight: float, height_cm: float) -> float:
    if height_cm <= 0:
        raise_zh_422("身高必须大于0。")
    return float(weight) / ((float(height_cm) / 100) ** 2)


def calc_loss_pct(records: Dict[str, float], month: str) -> float:
    """按距今月份计算相对当前体重的下降百分比。"""
    previous = float(records[month])
    current = float(records["0"])
    if previous <= 0:
        raise_zh_422(f"距今{month}个月体重必须大于0。")
    return (previous - current) / previous * 100


def nrs_nutrition_score(payload: NRS2002Request) -> Tuple[int, Dict[str, float], float]:
    records = payload.weight_records
    loss_1m = calc_loss_pct(records, "1")
    loss_2m = calc_loss_pct(records, "2")
    loss_3m = calc_loss_pct(records, "3")

    weight_score = 0
    if loss_1m > 5 and payload.general_condition_impaired:
        weight_score = 3
    elif loss_2m > 5 and payload.general_condition_impaired:
        weight_score = 2
    elif loss_3m > 5:
        weight_score = 1

    bmi = calc_bmi(records["0"], payload.height)
    bmi_score = 0
    if bmi < 18.5 and payload.general_condition_impaired:
        bmi_score = 3
    elif 18.5 <= bmi <= 20.5 and payload.general_condition_impaired:
        bmi_score = 2

    intake = payload.intake_last_week
    if intake <= 25:
        intake_score = 3
    elif intake <= 50:
        intake_score = 2
    elif intake <= 75:
        intake_score = 1
    else:
        intake_score = 0

    details = {
        "1m_loss_pct": round4(loss_1m),
        "2m_loss_pct": round4(loss_2m),
        "3m_loss_pct": round4(loss_3m),
    }
    return max(weight_score, bmi_score, intake_score), details, bmi


def disease_score_for_nrs(disease_ids: List[str]) -> int:
    disease_map = get_disease_map()
    if not disease_ids:
        return 0
    return max(int(disease_map[item].get("nrs_score", 0)) for item in disease_ids)


@app.get("/diseases")
def get_diseases() -> Dict[str, object]:
    return diseases_cache


@app.post("/assess/nrs2002")
def assess_nrs2002(payload: NRS2002Request) -> Dict[str, object]:
    validate_weight_records(payload.weight_records, REQUIRED_NRS_MONTHS)
    validate_disease_ids(payload.disease_ids)

    nutrition_score, loss_details, bmi = nrs_nutrition_score(payload)
    disease_score = disease_score_for_nrs(payload.disease_ids)
    age_score = 1 if payload.age >= 70 else 0
    total_score = nutrition_score + disease_score + age_score
    has_risk = total_score >= 3
    risk_level = "存在营养风险" if has_risk else "暂无营养风险"
    recommendation = (
        "建议启动营养支持流程，结合临床情况完善膳食评估、实验室检查和个体化营养干预。"
        if has_risk
        else "建议继续常规饮食管理与动态随访，如体重或摄食量下降应及时复评。"
    )

    return {
        "tool": "NRS-2002",
        "total_score": total_score,
        "nutrition_score": nutrition_score,
        "disease_score": disease_score,
        "age_score": age_score,
        "bmi": round4(bmi),
        "weight_loss_details": loss_details,
        "has_risk": has_risk,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "message": f"NRS-2002总分为{total_score}分，判定为：{risk_level}。{recommendation}",
    }


@app.post("/assess/mna_sf")
def assess_mna_sf(payload: MNASFRequest) -> Dict[str, object]:
    required = ("0",) if "3" not in payload.weight_records else ("0", "3")
    validate_weight_records(payload.weight_records, required)
    if payload.use_bmi:
        bmi = calc_bmi(payload.weight_records["0"], payload.height)
    else:
        if payload.calf_circumference is None or payload.calf_circumference <= 0:
            raise_zh_422("使用小腿围评估时，小腿围为必填且必须大于0。")
        bmi = calc_bmi(payload.weight_records["0"], payload.height)

    q1 = 0 if payload.intake_last_week <= 33 else 1 if payload.intake_last_week <= 66 else 2

    if "3" not in payload.weight_records:
        loss_kg = 0.0
        q2 = 1
    else:
        loss_kg = float(payload.weight_records["3"]) - float(payload.weight_records["0"])
        if loss_kg > 3:
            q2 = 0
        elif loss_kg > 0:
            q2 = 2
        else:
            q2 = 3

    q3 = payload.mobility
    q4 = 0 if payload.stress_or_acute_disease else 2
    q5 = payload.mental_status
    if payload.use_bmi:
        if bmi < 19:
            q6 = 0
        elif bmi <= 21:
            q6 = 1
        elif bmi <= 23:
            q6 = 2
        else:
            q6 = 3
    else:
        q6 = 0 if float(payload.calf_circumference) < 31 else 3

    total = q1 + q2 + q3 + q4 + q5 + q6
    if total >= 12:
        level = "营养正常"
    elif total >= 8:
        level = "营养不良风险"
    else:
        level = "营养不良"

    return {
        "tool": "MNA-SF",
        "total_score": total,
        "score_breakdown": {
            "q1_appetite": q1,
            "q2_weight_loss": q2,
            "q3_mobility": q3,
            "q4_stress": q4,
            "q5_mental": q5,
            "q6_bmi_or_calf": q6,
        },
        "bmi": round4(bmi),
        "weight_loss_3m_kg": round4(loss_kg),
        "level": level,
        "message": f"MNA-SF总分为{total}/14分，评估等级为：{level}。建议结合病史和饮食记录进行持续营养管理。",
    }


@app.post("/assess/glim")
def assess_glim(payload: GLIMRequest) -> Dict[str, object]:
    validate_weight_records(payload.weight_records, REQUIRED_GLIM_MONTHS)
    validate_disease_ids(payload.disease_ids)
    if payload.muscle_loss not in {"none", "mild_moderate", "severe"}:
        raise_zh_422("肌肉减少程度必须为 none、mild_moderate 或 severe。")

    disease_map = get_disease_map()
    bmi = calc_bmi(payload.weight_records["0"], payload.height)
    loss_6m = calc_loss_pct(payload.weight_records, "6")
    loss_over6m = calc_loss_pct(payload.weight_records, "12")

    phenotypic = []
    if loss_6m > 5 or loss_over6m > 10:
        phenotypic.append("非自主体重丢失")
    if (payload.age < 70 and bmi < 18.5) or (payload.age >= 70 and bmi < 20):
        phenotypic.append("低BMI")
    if payload.muscle_loss != "none":
        phenotypic.append("肌肉减少")

    etiological = []
    if payload.reduced_intake:
        etiological.append("摄食减少或消化吸收障碍")
    selected_diseases = [disease_map[item] for item in payload.disease_ids]
    if any(item.get("glim_type") in {"acute", "chronic"} for item in selected_diseases):
        etiological.append("炎症或疾病负担")
    if payload.crp != -1 and payload.crp >= 5:
        etiological.append("CRP升高")
    if payload.il6 != -1 and payload.il6 >= 7:
        etiological.append("IL-6升高")

    phenotypic_met = bool(phenotypic)
    etiological_met = bool(etiological)
    is_malnourished = phenotypic_met and etiological_met

    severity = None
    if is_malnourished:
        severe = (
            loss_6m > 10
            or loss_over6m > 20
            or (payload.age < 70 and bmi < 18.5)
            or (payload.age >= 70 and bmi < 20)
            or payload.muscle_loss == "severe"
        )
        moderate = (
            5 <= loss_6m <= 10
            or 10 <= loss_over6m <= 20
            or (payload.age < 70 and 18.5 <= bmi < 20)
            or (payload.age >= 70 and 20 <= bmi < 22)
            or payload.muscle_loss == "mild_moderate"
        )
        if severe:
            severity = "重度营养不良（2期）"
        elif moderate:
            severity = "中度营养不良（1期）"

    if is_malnourished:
        message = f"GLIM标准提示营养不良，严重程度为{severity or '需结合临床进一步分期'}。"
    else:
        message = "当前未同时满足GLIM表型标准和病因标准，暂不诊断为营养不良，建议动态随访。"

    return {
        "tool": "GLIM",
        "is_malnourished": is_malnourished,
        "phenotypic_met": phenotypic_met,
        "etiological_met": etiological_met,
        "phenotypic_criteria_triggered": phenotypic,
        "etiological_criteria_triggered": etiological,
        "bmi": round4(bmi),
        "weight_loss_6m_pct": round4(loss_6m),
        "weight_loss_over6m_pct": round4(loss_over6m),
        "severity": severity,
        "message": message,
    }


# =========================
# 草稿持久化接口（追加）
# =========================
from fastapi.responses import FileResponse

DRAFT_FILE = "./draft_data.json"
DRAFT_IMAGE_DIR = "./draft_images"
DRAFT_VIEWS = {"front", "left", "right"}


def default_draft_data() -> Dict[str, object]:
    """返回草稿初始结构，供初始化和清空草稿复用。"""
    return {
        "patient_info": {},
        "weight_records": {},
        "intake_records": {},
        "nrs2002_form": {},
        "mnasf_form": {},
        "glim_form": {},
        "images": {"front": None, "left": None, "right": None},
        "image_result": None,
        "nrs2002_result": None,
        "mnasf_result": None,
        "glim_result": None,
    }


@app.on_event("startup")
def init_draft_storage() -> None:
    """服务启动时确保草稿JSON和图片目录存在。"""
    try:
        image_dir = Path(DRAFT_IMAGE_DIR)
        image_dir.mkdir(parents=True, exist_ok=True)
        draft_path = Path(DRAFT_FILE)
        if not draft_path.exists():
            write_draft_file(default_draft_data())
    except Exception as exc:
        raise RuntimeError(f"初始化草稿存储失败：{exc}") from exc


def read_draft_file() -> Dict[str, object]:
    """以utf-8读取完整草稿文件。"""
    with open(DRAFT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def write_draft_file(data: Dict[str, object]) -> None:
    """以utf-8覆盖写入完整草稿文件。"""
    with open(DRAFT_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def ensure_draft_view(view: str) -> None:
    if view not in DRAFT_VIEWS:
        raise HTTPException(status_code=400, detail="图片视角只能是 front、left 或 right。")


def draft_image_path(view: str) -> Path:
    return Path(DRAFT_IMAGE_DIR) / f"{view}.jpg"


def draft_500(message: str, exc: Exception) -> None:
    raise HTTPException(status_code=500, detail=f"{message}：{exc}") from exc


@app.get("/draft")
def get_draft() -> Dict[str, object]:
    """读取并返回完整草稿。"""
    try:
        return read_draft_file()
    except Exception as exc:
        draft_500("读取草稿失败", exc)


@app.post("/draft")
def save_draft(data: Dict[str, object]) -> Dict[str, object]:
    """接收前端完整草稿并覆盖保存。"""
    try:
        write_draft_file(data)
        return {"saved": True}
    except Exception as exc:
        draft_500("保存草稿失败", exc)


@app.delete("/draft")
def clear_draft() -> Dict[str, object]:
    """重置草稿JSON，并清空草稿图片目录。"""
    try:
        image_dir = Path(DRAFT_IMAGE_DIR)
        image_dir.mkdir(parents=True, exist_ok=True)
        for image_file in image_dir.iterdir():
            if image_file.is_file():
                image_file.unlink()
        initial_data = default_draft_data()
        write_draft_file(initial_data)
        return initial_data
    except Exception as exc:
        draft_500("清空草稿失败", exc)


@app.post("/draft/image/{view}")
async def save_draft_image(view: str, file: UploadFile = File(...)) -> Dict[str, object]:
    """保存单个视角草稿图片，并更新草稿JSON中的图片状态。"""
    try:
        ensure_draft_view(view)
        validate_image_file(file, view)
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        Path(DRAFT_IMAGE_DIR).mkdir(parents=True, exist_ok=True)
        image.save(draft_image_path(view), format="JPEG", quality=95)

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


@app.get("/draft/image/{view}")
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


@app.delete("/draft/image/{view}")
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
