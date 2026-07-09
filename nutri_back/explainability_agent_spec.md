# 任务规格书：面部图像筛查 - 可解释性结果展示模块

## 0. 背景与已完成部分

`NutriProject` 是一个营养不良面部图像筛查系统（FastAPI后端 `nutri_back/` + Vue3前端 `nutri_front/`）。当前 `/predict`、`/predict/draft` 接口只返回分类概率，本任务要新增"可解释性结果展示"：对每个已上传的人脸视角（front/left/right），展示模型判断时关注的区域热力图，并给出一句话文字描述关注了哪些区域。

**以下文件已经就位，直接复用，不要重写：**

- `nutri_back/classify_model/models/lora.py` —— 已支持 `capture_attention`/`captured_attn`，梯度回溯所需的 attention 捕获机制已就绪。
- `nutri_back/classify_model/passing/qc_filter.py` + `nutri_back/classify_model/passing/face_landmarker.task` —— ROI landmark 提取所需的 `ClinicalFeatureExtractor` 及模型权重文件。
- `nutri_back/classify_model/roi_attention.py` —— 核心可解释性算法：
  - `ClassSpecificGradientRollout(model)(image_tensor, target_class="malnourished_face")` → 返回 `{"attn_map", "maps", "logits", "probs", "target_idx", "target_class"}`。**`target_class` 已被锁死为 `malnourished_face`，传其他值会 raise ValueError，不要试图绕过。**
  - `DynamicROIAttentionAnalyzer(use_insightface_fallback=False).generate_roi_masks(image_np, view_name)` → 返回 `{"temporal": mask, "orbital": mask, "malar": mask, "jawline": mask}` 或 `None`（landmark检测失败时）。`view_name` 接受 `"front"/"left"/"right"` 或 `"front"/"left_45"/"right_45"`（内部有别名映射，见 `_canonical_view_name`）。
  - `compute_roi_map_scores(attn_map, roi_masks)` → 返回打平字典，形如 `{"roi_temporal_mean": ..., "roi_temporal_enrichment": ..., ..., "focused_roi": "orbital", "focused_roi_enrichment": 1.3}`。
  - `draw_visualization(image, attn_map=..., return_base64=True)` → 返回 `data:image/png;base64,...` 格式的字符串（原图+热力图叠加，单张）。
- `nutri_back/classify_model/narrative_report.py` —— `build_attention_text(roi_scores: dict) -> str`，其中 `roi_scores` 期望格式是 `{"temporal": enrichment值, "orbital": enrichment值, "malar": enrichment值, "jawline": enrichment值}`（注意：跟 `compute_roi_map_scores` 的打平输出格式**不一致**，需要你在服务层做转换，见下方任务2）。

**已确认的产品决策（不要偏离）：**

1. 文字只描述"关注区域"，不做严重程度/病理判断。
2. 热力图每视角一张：原图 + 热力图叠加，不做多宫格科研图。
3. `target_class` 固定为 `malnourished_face`，不管最终预测是"正常"还是"营养不良"都展示该模块，前端文案要加区分性说明，例如："以下展示的是营养不良风险的关注依据，供参考"。
4. 本阶段目标是技术验证/demo，**不要求实时性能优化**（不用引入异步队列、GPU专属优化、缓存层等）。

**环境依赖：**

- `mediapipe` 已装。
- **请检查并确认 `tqdm` 是否已安装**（`qc_filter.py` 顶部有 `import tqdm`，是模块级导入，缺失会导致 `roi_attention.py` 无法导入）。如未安装，加入 requirements 并安装。
- `insightface` 不需要安装，`DynamicROIAttentionAnalyzer` 默认 `use_insightface_fallback=False`，不会触发其惰性 import。

---

## 1. 任务目标

新增一个 `POST /explain/roi` 接口和对应前端展示组件，输入用户已上传/已保存的三视角人脸图片，输出每个视角的热力图（base64）+ 关注区域文字说明。

---

## 2. 后端任务

### 2.1 新增 `nutri_back/services/explain_service.py`

职责：编排单张图片 → 梯度回溯 → ROI掩码 → 热力图 → 文字描述 的完整流程。

**关键实现细节（务必注意）：**

- **像素对齐是最容易出错的地方**：送入模型的 tensor（经过 `config.transform`：Resize 224 + CenterCrop 224 + ToTensor + Normalize）和送入 `generate_roi_masks`/`draw_visualization` 的 `image_np` 必须是**同一次 Resize+CenterCrop 之后**的图像内容，否则热力图和ROI掩码会和显示的图片错位。请参考 nutricode 的 `roi_attention_analysis.py` 里 `preprocess_for_model_and_roi` 的做法：先用 `Resize(224, BICUBIC) + CenterCrop(224)` 得到几何对齐的 224x224 PIL图（用于ROI/热力图），再对同一张图做 `ToTensor+Normalize` 得到模型输入 tensor。不要分别独立处理两条路径。
- 模型必须复用 `model_loader.py` 里已加载的全局 `model` 实例（避免重复加载权重）。
- 梯度回溯需要 `requires_grad_(True)` + `backward()`，这跟 `predict_one_view` 全程 `torch.no_grad()` 的路径不同，必须写成独立函数，不要复用/修改 `predict_one_view`。
- `ClassSpecificGradientRollout` 建议在服务模块加载时实例化一次并缓存（模型结构固定，不需要每次请求重新构造），`DynamicROIAttentionAnalyzer` 同理。
- **补上 `compute_roi_map_scores` 输出格式到 `build_attention_text` 输入格式的转换**，例如：
  ```python
  def _to_simple_enrichment(scores: dict) -> dict:
      return {roi: scores[f"roi_{roi}_enrichment"] for roi in ("temporal", "orbital", "malar", "jawline")}
  ```
- 单张图处理若失败（比如 `generate_roi_masks` 返回 `None`，landmark检测失败），该视角要返回明确的失败状态（例如 `{"status": "failed", "reason": "人脸关键点检测失败"}`），不要让整个请求因为一个视角失败而报500。其余视角正常返回。

对外提供一个函数，形如：

```python
def explain_single_view(image: PIL.Image, view_name: str) -> dict:
    """
    返回:
    {
      "status": "ok" | "failed",
      "heatmap_base64": "data:image/png;base64,...",  # status=failed时可为None
      "attention_text": "对眶周、颧颊区域关注度较高",
      "reason": None  # status=failed时填失败原因
    }
    """
```

### 2.2 新增 `nutri_back/routers/explain.py`

参考 `routers/predict.py` 的两个接口模式（直接上传 vs 读草稿图片），新增：

- `POST /explain/roi`：接受 `front`/`left`/`right` 三个可选 `UploadFile`（跟 `/predict` 参数一致），至少一张。
- `POST /explain/roi/draft`：直接用 `services/draft_service.py` 里已保存的草稿图片（跟 `/predict/draft` 逻辑一致）。

返回结构：

```json
{
  "target_class_note": "以下展示的是营养不良风险的关注依据，供参考",
  "views": {
    "front": {"status": "ok", "heatmap_base64": "...", "attention_text": "..."},
    "left":  {"status": "failed", "heatmap_base64": null, "attention_text": null, "reason": "人脸关键点检测失败"},
    "right": {"status": "ok", "heatmap_base64": "...", "attention_text": "..."}
  }
}
```

在 `app.py` 里把新 router include 进去（参考现有 router 的注册方式）。

### 2.3 不要改动

- `model_loader.py` 的 `predict_one_view`、`aggregate_scores`、`load_model` 逻辑不动。
- `config.py` 的 `CLASS_NAMES`/`POSITIVE_CLASS` 不动（`roi_attention.py` 已经在用）。
- `classify_model/models/clip.py` 不动（不需要 `use_roi_aux_head`）。

---

## 3. 前端任务

### 3.1 新增 `nutri_front/src/components/ExplainabilityPanel.vue`

- 在筛查结果展示后（参考 `ResultPanel.vue` 现有布局），新增一个可解释性结果区块。
- 三个视角用 tab 或并排卡片展示，每个卡片包含：热力图（`<img :src="heatmap_base64">`）+ 下方一行文字描述。
- 顶部展示 `target_class_note` 说明文案。
- 某视角 `status: "failed"` 时，该卡片展示"该视角未能生成可解释性结果：{reason}"，不影响其他视角展示。
- 调用时机：跟现有 `/predict` 或 `/predict/draft` 调用同批触发，或者在展示完分类结果后追加一次 `/explain/roi(/draft)` 请求即可（本阶段不要求两者合并成一个接口，允许前端分两次请求）。

---

## 4. 验收标准

1. 上传三视角图片（或走草稿流程）后，`/explain/roi` 或 `/explain/roi/draft` 能正常返回三个视角的热力图+文字，某一视角landmark检测失败时不影响其余视角。
2. 热力图肉眼可见与对应人脸图像空间对齐（重点检查这一条，是最容易出错的地方）。
3. 文字描述只包含关注区域信息（如"对眶周、颧颊区域关注度较高"或"未见关注度显著高于阈值的预设区域"），不包含任何严重程度/病理描述。
4. 前端能展示区分性说明文案，且预测为"正常"的受试者也能正常看到该模块。
5. 不要引入训练集校准阈值、`roi_descriptor.py` 相关逻辑、批量报告生成逻辑——这些都不在本次任务范围内。

## 5. 明确不做的事（非目标）

- 不做严重程度/病理判断文字。
- 不做实时性能优化（无需异步队列、结果缓存、GPU专属加速）。
- 不接入 `insightface` 侧脸兜底（保持 `use_insightface_fallback=False`）。
- 不修改任何模型 checkpoint 或训练相关代码。
