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
# CHECKPOINT_PATH = "./classify_model/weight/best_checkpoint.pth"
# SZJ的
CHECKPOINT_PATH = "./classify_model/weight2/best_checkpoint.pth"
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
