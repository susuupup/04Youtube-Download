from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, Depends
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

# 静态文件和模板配置
if not os.environ.get("VERCEL"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    # Vercel 环境下使用不同的静态文件配置
    app.mount("/static", StaticFiles(directory="/tmp/static"), name="static")
    # 确保目录存在
    os.makedirs("/tmp/static/videos", exist_ok=True)

templates = Jinja2Templates(directory="templates")

# 添加自定义过滤器
def get_basename(path):
    return os.path.basename(path)

templates.env.filters["basename"] = get_basename

# 加载视频信息
def load_videos_info():
    try:
        if os.path.exists(VIDEOS_INFO_FILE):
            with open(VIDEOS_INFO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return []

# 保存视频信息
def save_videos_info(videos_info):
    try:
        with open(VIDEOS_INFO_FILE, 'w', encoding='utf-8') as f:
            json.dump(videos_info, f, ensure_ascii=False, indent=2)
    except:
        pass

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

# 修改WebSocket路由
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        print("新的WebSocket连接请求")
        await websocket.accept()
        print("WebSocket连接已接受")
        
        # 等待接收视频URL
        data = await websocket.receive_text()
        video_url = unquote(data).strip()
        print(f"收到视频URL: {video_url}")

        # yt-dlp配置
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'extract_flat': True,  # 只获取元数据
            'skip_download': True, # 不下载视频
        }

        # 获取视频信息
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print("获取视频信息...")
                info = ydl.extract_info(video_url, download=False)
                
                if not info:
                    raise Exception("无法获取视频信息")
                
                video_info = {
                    'id': info['id'],
                    'title': info['title'],
                    'author': info.get('uploader', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'description': info.get('description', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'webpage_url': info.get('webpage_url', video_url),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'download_time': datetime.now().isoformat()
                }
                
                videos = load_videos_info()
                videos.append(video_info)
                save_videos_info(videos)
                
                await websocket.send_json({
                    'status': 'complete',
                    'video_info': video_info
                })
                print("信息获取完成")

        except Exception as e:
            error_msg = f"错误: {str(e)}"
            print(error_msg)
            await websocket.send_json({
                'status': 'error',
                'message': error_msg
            })

    except WebSocketDisconnect:
        print("WebSocket连接断开")
    except Exception as e:
        error_msg = f"发生错误: {str(e)}"
        print(error_msg)
        try:
            await websocket.send_json({
                'status': 'error',
                'message': error_msg
            })
        except:
            print("无法发送错误消息")
    finally:
        try:
            await websocket.close()
        except:
            pass

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