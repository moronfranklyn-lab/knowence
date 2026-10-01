#!/usr/bin/env bash
# ============================================================================
#  下载本地模型并放进 Docker 原生卷
#
#  为什么不能简单地把模型放在宿主机目录挂进去：
#    llama.cpp 用 mmap 读权重，跨宿主/容器的共享挂载会让 mmap 退化成
#    逐次读盘 —— 实测推理速度差 9.4 倍（2.0 tok/s vs 18.7 tok/s）。
#    所以模型必须落在 Docker 原生卷里。见 docs/阶段文档/本地部署实录.md 坑 7
#
#  用法：
#      ./scripts/download-models.sh              # 下载两个模型（约 6GB）
#      ./scripts/download-models.sh --embed-only # 只下向量模型（约 1.1GB）
# ============================================================================
set -euo pipefail

VOLUME="${MODELS_VOLUME:-knowence-models}"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

# ModelScope 国内快源（官方仓库实测 ~186KB/s，这里 ~10-27MB/s）
MS="https://modelscope.cn/api/v1/models"

EMBED_NAME="bge-m3-FP16.gguf"
EMBED_URL="$MS/gpustack/bge-m3-GGUF/repo?Revision=master&FilePath=bge-m3-FP16.gguf"

RERANK_NAME="bge-reranker-v2-m3-FP16.gguf"
RERANK_URL="$MS/gpustack/bge-reranker-v2-m3-GGUF/repo?Revision=master&FilePath=bge-reranker-v2-m3-FP16.gguf"

EMBED_ONLY=0
[[ "${1:-}" == "--embed-only" ]] && EMBED_ONLY=1

echo "==> 目标卷：$VOLUME"
docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null
echo "    卷已就绪"

fetch() {
  local url="$1" out="$2" label="$3"
  if [[ -s "$TMPDIR/$out" ]]; then
    echo "==> $label 已存在，跳过"
    return
  fi
  echo "==> 下载 $label ..."
  curl -L --retry 5 --retry-delay 3 -C - -o "$TMPDIR/$out" "$url"
  local size
  size=$(du -h "$TMPDIR/$out" | cut -f1)
  echo "    完成：$size"
}

fetch "$EMBED_URL" "$EMBED_NAME" "向量模型 bge-m3（约 1.1GB）"
if [[ "$EMBED_ONLY" -eq 0 ]]; then
  fetch "$RERANK_URL" "$RERANK_NAME" "重排模型 bge-reranker-v2-m3（约 1.1GB）"
fi

echo "==> 复制进 Docker 卷（这一步不经过网络，是本地拷贝）..."
docker run --rm \
  -v "$VOLUME":/dest \
  -v "$TMPDIR":/src:ro \
  alpine sh -c "
    cp -v /src/*.gguf /dest/ &&
    echo '--- 卷内文件 ---' &&
    ls -lh /dest/
  "

echo
echo "✅ 完成。卷 $VOLUME 内容："
docker run --rm -v "$VOLUME":/dest alpine ls -lh /dest/
echo
echo "接下来：docker compose up -d"
