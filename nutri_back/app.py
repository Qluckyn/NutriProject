from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

import model_loader
from routers import analysis, assess, diseases, draft, explain, history, predict, reports
from services import diseases_service, draft_service, history_service

# FastAPI应用入口：只负责实例创建、中间件、异常处理、路由挂载和启动初始化。
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
    # 允许前端读取下载响应的 Content-Disposition，保留后端生成的真实文件名。
    expose_headers=["Content-Disposition"],
)


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


app.include_router(predict.router)
app.include_router(assess.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(history.router)
app.include_router(draft.router)
app.include_router(explain.router)
app.include_router(diseases.router)


@app.on_event("startup")
def startup() -> None:
    model_loader.load_model()
    diseases_service.load_diseases_config()
    draft_service.init_draft_storage()
    history_service.init_history_storage()
