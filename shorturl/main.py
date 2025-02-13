from contextlib import asynccontextmanager
import secrets
import string
import random
from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.sql.ddl import CreateTable

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import List
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 配置信息
DATABASE_URL = os.getenv("DATABASE_URL").replace("mysql://", "mysql+aiomysql://", 1)

SHORT_URL_DOMAIN = os.getenv("SHORT_URL_DOMAIN", "http://localhost:8000")
SHORT_CODE_LENGTH = int(os.getenv("SHORT_CODE_LENGTH", 6))

# 异步数据库配置
engine = create_async_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

templates = Jinja2Templates(directory="shorturl/templates")



# 数据库模型
class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(10), unique=True, index=True, nullable=False) 
    original_url = Column(String(2083), nullable=False)
    clicks = Column(Integer, default=0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在启动时创建表
    try:
        async with engine.begin() as conn:
            # 使用 CreateTable 创建表
            table = URL.__table__
            await conn.execute(CreateTable(table, if_not_exists=True))
            print("Table 'urls' created successfully.")
    except Exception as e:
        print(f"Error creating table: {e}")
        raise e
    
    yield
    await engine.dispose()
    
app = FastAPI(lifespan=lifespan)  # 将 lifespan 事件与应用绑定

# 请求模型
class URLRequest(BaseModel):
    original_url: str
    length: int = Field(default=SHORT_CODE_LENGTH, ge=4, le=10)


class BulkURLRequest(BaseModel):
    urls: List[str]
    length: int = Field(default=SHORT_CODE_LENGTH, ge=4, le=10)

# 依赖项
async def get_db():
    async with SessionLocal() as db:
        yield db

# 工具函数
async def generate_short_code(length: int, db: AsyncSession):
    characters = string.ascii_letters + string.digits
    while True:
        short_code = ''.join(random.choices(characters, k=length))
        result = await db.execute(select(URL).filter(URL.short_code == short_code))
        if not result.scalar_one_or_none():
            return short_code

# 路由
@app.post("/shorten/")
async def shorten_url(
    request: URLRequest,
    db: AsyncSession = Depends(get_db)
):
    if not request.original_url.startswith(("http://", "https://")):
        raise HTTPException(400, detail="Invalid URL format")
    
    short_code = await generate_short_code(request.length, db)
    new_url = URL(short_code=short_code, original_url=request.original_url)
    db.add(new_url)
    await db.commit()
    return {"short_url": f"{SHORT_URL_DOMAIN}/{short_code}"}

@app.post("/shorten/bulk/")
async def shorten_bulk_url(
    request: BulkURLRequest,
    db: AsyncSession = Depends(get_db)
):
    url_entries = []
    short_urls = []
    
    for url in request.urls:
        if not url.startswith(("http://", "https://")):
            continue
        short_code = await generate_short_code(request.length, db)
        url_entries.append(URL(short_code=short_code, original_url=url))
        short_urls.append({"original_url": url, "short_url": f"{SHORT_URL_DOMAIN}/{short_code}"})
    
    db.add_all(url_entries)
    await db.commit()
    return short_urls

@app.get("/{short_code}")
async def redirect_url(
    short_code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(URL).filter(URL.short_code == short_code))
    url_entry = result.scalar_one_or_none()
    
    if not url_entry:
        raise HTTPException(404, detail="Short URL not found")
    
    background_tasks.add_task(update_clicks, url_entry.id)
    return RedirectResponse(url=url_entry.original_url)

async def update_clicks(url_id: int):
    async with SessionLocal() as db:
        result = await db.execute(select(URL).filter(URL.id == url_id))
        url_entry = result.scalar_one_or_none()
        if url_entry:
            url_entry.clicks += 1
            await db.commit()

# 认证路由
security = HTTPBasic()
ADMIN_CREDS = (
    os.getenv("ADMIN_USERNAME", "admin"),
    os.getenv("ADMIN_PASSWORD", "admin")
)

@app.get("/shorturl/private", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security)
):
    if not (
        secrets.compare_digest(credentials.username, ADMIN_CREDS[0]) and
        secrets.compare_digest(credentials.password, ADMIN_CREDS[1])
    ):
        raise HTTPException(
            401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return templates.TemplateResponse("index.html", {"request": request})