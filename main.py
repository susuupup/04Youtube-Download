from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import json
import os
import asyncio
from datetime import datetime
import yt_dlp
from pathlib import Path
from urllib.parse import unquote
from starlette.websockets import WebSocketState

# 创建连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket连接已建立, 当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"WebSocket连接已断开, 当前连接数: {len(self.active_connections)}")

    async def send_message(self, message: dict, websocket: WebSocket):
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(message)

# 创建全局连接管理器实例
manager = ConnectionManager()

app = FastAPI()

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 根据环境设置路径
if os.environ.get("VERCEL"):
    # Vercel 环境使用 /tmp 目录
    BASE_DIR = Path("/tmp")
    STATIC_DIR = BASE_DIR / "static"
    VIDEOS_DIR = STATIC_DIR / "videos"
    VIDEOS_INFO_FILE = BASE_DIR / "videos_info.json"
else:
    # 本地环境使用项目目录
    BASE_DIR = Path(".")
    STATIC_DIR = BASE_DIR / "static"
    VIDEOS_DIR = STATIC_DIR / "videos"
    VIDEOS_INFO_FILE = BASE_DIR / "videos_info.json"

# 确保目录存在
STATIC_DIR.mkdir(exist_ok=True, parents=True)
VIDEOS_DIR.mkdir(exist_ok=True, parents=True)

# 静态文件和模板配置
if not os.environ.get("VERCEL"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory="templates")

# 添加自定义过滤器
def get_basename(path):
    return os.path.basename(path)

templates.env.filters["basename"] = get_basename

# 加载视频信息
def load_videos_info():
    try:
        if VIDEOS_INFO_FILE.exists():
            return json.loads(VIDEOS_INFO_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"加载视频信息失败: {e}")
    return []

# 保存视频信息
def save_videos_info(videos_info):
    try:
        VIDEOS_INFO_FILE.write_text(json.dumps(videos_info, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"保存视频信息失败: {e}")

# 主页路由
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    videos = load_videos_info()
    # 按下载时间排序并只返回最近3个
    videos.sort(key=lambda x: x['download_time'], reverse=True)
    recent_videos = videos[:3]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "videos": recent_videos}
    )

# 添加新的 API 路由
@app.post("/api/download")
async def download_video(video_url: str = Form(...)):
    try:
        print(f"收到视频URL: {video_url}")
        
        # yt-dlp配置
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # 更具体的格式选择
            'quiet': False,
            'no_warnings': False,
            'extract_info': True,
            'verbose': True,
            'force_generic_extractor': False,
            'youtube_include_dash_manifest': False,  # 禁用 DASH manifest
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': 'https://www.youtube.com'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("获取视频信息...")
            info = ydl.extract_info(video_url, download=False)
            if not info:
                raise Exception("无法获取视频信息")
            
            # 获取直接下载链接
            formats = info.get('formats', [])
            if not formats:
                raise Exception("无法获取视频格式信息")
            
            # 尝试获取任何可用的格式
            download_url = None
            for f in reversed(formats):  # 从后往前找，通常质量更好
                if f.get('url'):
                    download_url = f.get('url')
                    break
            
            if not download_url:
                raise Exception("无法获取下载链接")
            
            # 构建文件名
            filename = f"{info['title']} - {info.get('uploader', 'Unknown')}"
            
            video_info = {
                'id': info['id'],
                'title': info['title'],
                'author': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
                'filesize': info.get('filesize', 0) or info.get('approximate_filesize', 0),
                'download_url': download_url,
                'filename': filename,
                'download_time': datetime.now().isoformat()
            }
            
            videos = load_videos_info()
            videos.append(video_info)
            videos = sorted(videos, key=lambda x: x['download_time'], reverse=True)[:3]
            save_videos_info(videos)
            
            return {"status": "success", "video_info": video_info}

    except Exception as e:
        return {"status": "error", "message": str(e)}

# 添加删除视频的路由
@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    try:
        videos = load_videos_info()
        # 找到要删除的视频
        video_to_delete = None
        for video in videos:
            if video['id'] == video_id:
                video_to_delete = video
                break
        
        if video_to_delete:
            # 删除文件
            try:
                os.remove(video_to_delete['filepath'])
            except:
                pass  # 如果文件已经不存在，忽略错误
            
            # 从列表中移除
            videos.remove(video_to_delete)
            save_videos_info(videos)
            return {"status": "success"}
        
        return {"status": "error", "message": "视频不存在"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000) 