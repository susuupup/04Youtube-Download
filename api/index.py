import sys
import os
from pathlib import Path

# 设置环境变量
os.environ["VERCEL"] = "1"

# 添加项目根目录到 Python 路径
sys.path.append(str(Path(__file__).parent.parent))

# 导入并导出 app
from main import app 