import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置 Vercel 环境变量
os.environ["VERCEL"] = "1"

# 导入并导出 app
from main import app 