from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

# =========================
# 集中配置
# =========================
# 模型推理、疾病配置和草稿存储等跨模块常量统一放在此处。
# YHQ的
CHECKPOINT_PATH = "./classify_model/weight/best_checkpoint.pth"
# CHECKPOINT_PATH = (
#     "/root/autodl-tmp/runs/ablation/classify_outputs/"
#     "clip_real_plus_synth_qc_pool0.7_nipc330_lr1e-5_nomix/"
#     "my_dataset/clipViT-B/16/n_img_per_cls_500/sd2.1/"
#     "shot20_seed0_template1_ddlr0.0001_ddep240_lbd0.8/"
#     "lr1e-05_wd0.0001_mixuag/best_checkpoint.pth"
# )
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

DRAFT_FILE = "./draft_data.json"
DRAFT_IMAGE_DIR = "./draft_images"
DRAFT_VIEWS = {"front", "left", "right"}

DISEASES_PATH = "./diseases.json"
REQUIRED_NRS_MONTHS = ("0", "1", "2", "3")
REQUIRED_GLIM_MONTHS = ("0", "6", "12")

GLIM_GI_SYMPTOM_LABELS = {
    "dysphagia": "吞咽困难",
    "nausea_vomiting": "恶心、呕吐",
    "diarrhea": "腹泻",
    "constipation": "便秘",
    "abdominal_pain": "腹痛",
    "other": "其他慢性胃肠症状",
}
GLIM_NUTRITION_IMPACT_LABELS = {
    "short_bowel": "短肠综合征",
    "pancreatic_insufficiency": "胰腺功能不全",
    "post_bariatric": "减肥手术后",
    "esophageal_stricture": "食管狭窄",
    "gastroparesis": "胃轻瘫",
    "intestinal_obstruction": "肠梗阻",
    "diarrhea_or_steatorrhea": "腹泻或脂肪痢",
    "high_output_stoma": "排出量较大的肠道造口",
    "other": "其他相关消化吸收疾病",
}
GLIM_ACUTE_DISEASE_IDS = {"severe_infection", "burn", "trauma", "brain_injury"}
GLIM_CHRONIC_DISEASE_IDS = {
    "malignant_tumor",
    "copd",
    "heart_failure",
    "ckd",
    "chronic_liver",
    "liver_cirrhosis",
    "rheumatoid_arthritis",
    "other",
}
GLIM_CHRONIC_DISEASE_LABELS = {"other": "其他"}
