#!/bin/bash
# Iuxis — Local-first AI Chief of Staff
# Single-command launcher: ./start.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

IUXIS_DIR="$(cd "$(dirname "$0")" && pwd)"
INBOX_DIR="${IUXIS_INBOX:-$HOME/iuxis-inbox}"

echo -e "${BLUE}🧠 Iuxis — Starting up...${NC}"
echo ""

# ── 1. Check Python ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}✗ Python 3 not found. Install Python 3.11+ first.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"

# ── 2. Check Node.js ─────────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo -e "${RED}✗ Node.js not found. Install Node.js 18+ first.${NC}"
    exit 1
fi

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓${NC} Node.js $NODE_VERSION"

# ── 3. Check Ollama ──────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo -e "${RED}✗ Ollama not found. Install from https://ollama.com${NC}"
    exit 1
fi

# Start Ollama if not running
if ! curl -s http://localhost:11434/ &>/dev/null; then
    echo -e "${YELLOW}Starting Ollama...${NC}"
    ollama serve &>/dev/null &
    sleep 2
fi
echo -e "${GREEN}✓${NC} Ollama running"

# ── 4. Check required models ─────────────────────────────────────
MODELS_INSTALLED=$(ollama list 2>/dev/null | awk '{print $1}')

if ! echo "$MODELS_INSTALLED" | grep -q "nomic-embed-text"; then
    echo -e "${YELLOW}Pulling nomic-embed-text (required for search)...${NC}"
    ollama pull nomic-embed-text
fi
echo -e "${GREEN}✓${NC} nomic-embed-text ready"

# Check for a generation model
HAS_GEN_MODEL=false
for model in qwen2.5:32b qwen2.5:14b qwen2.5:7b llama3.1:8b deepseek-r1:32b; do
    if echo "$MODELS_INSTALLED" | grep -q "$model"; then
        echo -e "${GREEN}✓${NC} Generation model: $model"
        HAS_GEN_MODEL=true
        break
    fi
done

if [ "$HAS_GEN_MODEL" = false ]; then
    echo -e "${YELLOW}⚠ No generation model found. Pulling qwen2.5:14b (recommended minimum)...${NC}"
    echo -e "${YELLOW}  This may take a few minutes on first run.${NC}"
    ollama pull qwen2.5:14b
    echo -e "${GREEN}✓${NC} qwen2.5:14b ready"
fi

# ── 5. Create directories ────────────────────────────────────────
mkdir -p "$INBOX_DIR"
mkdir -p "$IUXIS_DIR/data"
mkdir -p "$HOME/.iuxis/vectors"
echo -e "${GREEN}✓${NC} Directories ready (inbox: $INBOX_DIR)"

# ── 6. Install Python deps if needed ─────────────────────────────
if ! python3 -c "import fastapi" &>/dev/null; then
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    pip install -r "$IUXIS_DIR/requirements.txt" --break-system-packages -q
fi
echo -e "${GREEN}✓${NC} Python dependencies"

# ── 7. Install frontend deps if needed ────────────────────────────
if [ ! -d "$IUXIS_DIR/iuxis-web/node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies (first run only)...${NC}"
    cd "$IUXIS_DIR/iuxis-web" && npm install --silent
fi
echo -e "${GREEN}✓${NC} Frontend dependencies"

# ── 8. Copy example config if none exists ─────────────────────────
if [ ! -f "$IUXIS_DIR/config.yaml" ]; then
    cp "$IUXIS_DIR/config.example.yaml" "$IUXIS_DIR/config.yaml"
    echo -e "${YELLOW}Created config.yaml from template — edit to customize.${NC}"
fi

# ── 9. Launch services ───────────────────────────────────────────
echo ""
echo -e "${BLUE}Starting services...${NC}"

# Backend
cd "$IUXIS_DIR"
uvicorn iuxis_api.main:app --reload --port 8000 &>/dev/null &
BACKEND_PID=$!
sleep 2

if kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Backend running on http://localhost:8000"
else
    echo -e "${RED}✗ Backend failed to start. Run manually: uvicorn iuxis_api.main:app --reload --port 8000${NC}"
    exit 1
fi

# Frontend
cd "$IUXIS_DIR/iuxis-web"
npm run dev -- -p 3000 &>/dev/null &
FRONTEND_PID=$!
sleep 3

if kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Frontend running on http://localhost:3000"
else
    echo -e "${RED}✗ Frontend failed to start. Run manually: cd iuxis-web && npm run dev${NC}"
fi

# ── 10. Open browser ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}🧠 Iuxis is ready!${NC}"
echo -e "   Dashboard:  ${BLUE}http://localhost:3000${NC}"
echo -e "   API:        ${BLUE}http://localhost:8000/docs${NC}"
echo -e "   Inbox:      ${BLUE}$INBOX_DIR${NC}"
echo ""
echo -e "Drop project files into ${BLUE}$INBOX_DIR${NC} to start ingesting."
echo -e "Press ${RED}Ctrl+C${NC} to stop all services."
echo ""

# Open browser (macOS)
if command -v open &>/dev/null; then
    sleep 1
    open "http://localhost:3000"
fi

# ── Cleanup on exit ──────────────────────────────────────────────
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down Iuxis...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Done. See you next time.${NC}"
}

trap cleanup EXIT INT TERM

# Wait for either process to exit
wait
