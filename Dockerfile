# 安幕诺家族 · 小红 🌹 交易系统
# 基于 Python 3.11 + Tushare + AKShare
FROM python:3.11-slim-bookworm

LABEL maintainer="安幕诺家族"
LABEL description="小红 AI 股票交易辅助系统 v2.0"

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake \
    libta-lib-dev \
    wget curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 TA-Lib
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.6.0-src.tar.gz \
    && tar -xzf ta-lib-0.6.0-src.tar.gz \
    && cd ta-lib-0.6.0-src \
    && ./configure --prefix=/usr \
    && make -j$(nproc) \
    && make install \
    && cd .. && rm -rf ta-lib-0.6.0-src*

# 工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data /app/reports /app/logs /app/workspace

# 非 root 用户
RUN useradd -m -s /bin/bash xiaohong && chown -R xiaohong:xiaohong /app
USER xiaohong

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TQDM_DISABLE=1
ENV HERMES_HOME=/app

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python3 -c "from scripts.data_pipeline import get_index_data; print(get_index_data().get('asia',{}).get('shanghai','OK'))"

# 默认命令：Paper Trading 模式
CMD ["python3", "-m", "scripts.auto_executor", "--paper"]
