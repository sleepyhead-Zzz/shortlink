import base64
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI()

# 使用当前文件所在目录下的 templates 文件夹
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 外部短链接 API 地址（根据实际情况修改）
API_URL = "https://s.ops.ci/short"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    GET 请求：返回初始页面，只有输入区域。
    """
    return templates.TemplateResponse("index.html", {"request": request, "results": None, "urls": ""})


@app.post("/", response_class=HTMLResponse)
async def generate(request: Request, urls: str = Form(...)):
    """
    POST 请求：处理用户输入的长链接，每行一个，
    调用外部接口生成短链接，并提取响应中的 ShortUrl 字段，
    最后将所有短链接按行拼接后传递给模板。
    """
    # 分割输入的长链接，每行一个，过滤空行
    url_list = [line.strip() for line in urls.splitlines() if line.strip()]
    results = []

    for long_url in url_list:
        # 对长链接进行 Base64 编码
        encoded_long_url = base64.b64encode(long_url.encode()).decode()
        files = {
            "longUrl": (None, encoded_long_url),
            "shortKey": (None, "")  # 留空，由 API 自动生成
        }
        try:
            response = requests.post(API_URL, files=files)
            if response.status_code == 200:
                # 解析 JSON 响应，提取 ShortUrl 字段
                try:
                    data = response.json()
                    short_url = data.get("ShortUrl", "错误：返回数据中无 ShortUrl")
                except Exception as e:
                    short_url = f"错误：解析响应失败 ({e})"
            else:
                short_url = f"错误：状态码 {response.status_code}"
        except Exception as e:
            short_url = f"异常：{e}"
        results.append(short_url)

    # 将所有短链接按行拼接
    result_text = "\n".join(results)
    return templates.TemplateResponse("index.html", {"request": request, "results": result_text, "urls": urls})
