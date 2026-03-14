"""命令行入口：启动 FastAPI 后端服务。"""
from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
