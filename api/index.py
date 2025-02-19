import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from main import app

# 配置静态文件和模板
app.mount("/static", StaticFiles(directory="static"), name="static")

# 导出 app 供 Vercel 使用
app = app 