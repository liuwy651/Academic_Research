FROM python:3.11-slim

# 系统依赖：curl（健康检查用）、libgomp（pymupdf/numpy 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（与本地开发环境保持一致）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 依赖层单独缓存：仅在 pyproject.toml / uv.lock 变化时重新安装
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY . .

# 运行时目录
RUN mkdir -p uploads app/static/plots

# matplotlib 无头模式（Math_Analyst 绘图不依赖显示器）
ENV MPLBACKEND=Agg

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
