#!/bin/bash
set -e

# ── 等待 PostgreSQL 就绪 ──────────────────────────────────────────────
echo "==> Waiting for PostgreSQL..."
uv run python - <<'EOF'
import asyncio, asyncpg, os, sys

async def wait():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    for i in range(30):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("PostgreSQL is ready.")
            return
        except Exception as e:
            print(f"  [{i+1}/30] not ready: {e}")
            await asyncio.sleep(2)
    print("ERROR: PostgreSQL did not become ready in 60s.")
    sys.exit(1)

asyncio.run(wait())
EOF

# ── 等待 Milvus 就绪 ──────────────────────────────────────────────────
echo "==> Waiting for Milvus..."
uv run python - <<'EOF'
import time, sys, os
host = os.environ.get("MILVUS_HOST", "milvus")
port = int(os.environ.get("MILVUS_PORT", "19530"))
for i in range(30):
    try:
        from pymilvus import connections
        connections.connect(alias="health_check", host=host, port=port)
        connections.disconnect("health_check")
        print("Milvus is ready.")
        sys.exit(0)
    except Exception as e:
        print(f"  [{i+1}/30] not ready: {e}")
        time.sleep(3)
print("ERROR: Milvus did not become ready in 90s.")
sys.exit(1)
EOF

# ── 数据库迁移 ────────────────────────────────────────────────────────
echo "==> Running database migrations..."
uv run alembic upgrade head

# ── 启动服务 ──────────────────────────────────────────────────────────
echo "==> Starting backend server..."
exec uv run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
