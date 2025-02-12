from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import random
import string
from typing import List
from dotenv import load_dotenv
import os

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中读取配置
DATABASE_URL = os.getenv("DATABASE_URL")
SHORT_URL_DOMAIN = os.getenv("SHORT_URL_DOMAIN", "http://localhost:8000")
SHORT_CODE_LENGTH = int(os.getenv("SHORT_CODE_LENGTH", 6))

# 数据库连接设置
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

templates = Jinja2Templates(directory="shorturl/templates")

app = FastAPI()

class URL(Base):
    __tablename__ = "urls"
    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(10), unique=True, index=True, nullable=False)
    original_url = Column(String(2083), nullable=False)

def create_tables():
    Base.metadata.create_all(bind=engine)

create_tables()

class URLRequest(BaseModel):
    original_url: str
    length: int = SHORT_CODE_LENGTH  # 使用从配置文件读取的默认长度

class BulkURLRequest(BaseModel):
    urls: List[str]
    length: int = Field(default=SHORT_CODE_LENGTH, ge=4, le=10)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_short_code(length=SHORT_CODE_LENGTH, db=None):
    characters = string.ascii_letters + string.digits
    while True:
        short_code = ''.join(random.choices(characters, k=length))
        if not db or not db.query(URL).filter(URL.short_code == short_code).first():
            return short_code

@app.post("/shorten/")
def shorten_url(request: URLRequest, db: Session = Depends(get_db)):
    if not request.original_url.startswith("http://") and not request.original_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    short_code = generate_short_code(request.length, db=db)
    new_url = URL(short_code=short_code, original_url=request.original_url)
    db.add(new_url)
    db.commit()
    db.refresh(new_url)
    return {"short_url": f"{SHORT_URL_DOMAIN}/{short_code}"}  # 使用配置的 URL 域名

@app.post("/shorten/bulk/")
def shorten_bulk_url(request: BulkURLRequest, db: Session = Depends(get_db)):
    short_urls = []
    for url in request.urls:
        if not url.startswith("http://") and not url.startswith("https://"):
            continue
        short_code = generate_short_code(request.length, db=db)
        new_url = URL(short_code=short_code, original_url=url)
        db.add(new_url)
        db.commit()
        db.refresh(new_url)
        short_urls.append({"original_url": url, "short_url": f"{SHORT_URL_DOMAIN}/{short_code}"})
    return short_urls

@app.get("/{short_code}")
def redirect_url(short_code: str, db: Session = Depends(get_db)):
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return RedirectResponse(url=url_entry.original_url)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
