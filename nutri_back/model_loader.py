import io
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from config import (
    CHECKPOINT_PATH,
    CLASS_NAMES,
    DEVICE,
    POSITIVE_CLASS,
    SUPPORTED_EXTENSIONS,
    VIEW_LABELS,
    transform,
)

# 将训练代码目录加入导入路径，保证模型结构与训练阶段一致。
sys.path.insert(0, "./classify_model")
from models.clip import CLIP as NutriCLIP  # noqa: E402


# 模型加载、图像预处理、单视角推理等模型相关逻辑集中在此模块。
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
    # loralib.MergedLinear 在切换 eval 时会合并 LoRA 权重；
    # 先进入 eval 再加载 checkpoint，避免加载后再次 merge 造成概率漂移。
    current_model = current_model.to(DEVICE).eval()
    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=False)
    current_model.load_state_dict(checkpoint["model"], strict=False)
    model = current_model
