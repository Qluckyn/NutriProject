# 旧版 API 弃用说明

会话版接口由 `routers/session_api.py` 提供，是当前前端唯一使用的接口。它以 `session_id` 与 `assessment_id` 隔离草稿，并负责量表、筛查、历史记录和报告下载。

以下旧模块仍暂时保留，以免影响未知的外部调用；其路由在 OpenAPI 中标记为 `deprecated`，不得用于新功能：

- `routers/analysis.py`
- `routers/assess.py`
- `routers/draft.py`
- `routers/explain.py`
- `routers/history.py`
- `routers/reports.py`
- `routers/predict.py` 中除 `/health`、`/info` 外的旧预测接口

迁移期结束后，应先通过访问日志确认无调用，再从 `app.py` 取消挂载旧路由，最后删除对应旧的全局草稿与历史服务。
