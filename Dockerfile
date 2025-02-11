# 使用官方 Python 3.10 镜像
FROM python:3.10

# 设置工作目录
WORKDIR /app

# 安装 Poetry
RUN pip install poetry

# 复制 pyproject.toml 和 poetry.lock 以利用 Docker 缓存
COPY pyproject.toml poetry.lock /app/

# 安装依赖（不安装项目自身）
RUN poetry install --no-root --no-interaction --no-ansi

# 复制所有代码到容器
COPY . .

# 进入 shorturl 目录运行 FastAPI 服务器
CMD ["poetry", "run", "uvicorn", "shorturl.main:app", "--host", "0.0.0.0", "--port", "8000"]
