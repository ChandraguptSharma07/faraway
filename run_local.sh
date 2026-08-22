#!/usr/bin/env bash

# Ensure we're in the project root
cd "$(dirname "$0")"

echo "Initializing setup..."

# 1. Setup Backend Environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# Fix for NixOS: provide standard C++ and zlib libraries for pip-installed wheels
if [ -f /etc/os-release ] && grep -qi nixos /etc/os-release; then
    echo "NixOS detected. Setting up LD_LIBRARY_PATH for PyPI binaries..."
    export LD_LIBRARY_PATH="$(nix-build '<nixpkgs>' -A stdenv.cc.cc.lib -A zlib --no-out-link 2>/dev/null | sed 's/$/\/lib/' | paste -sd ':' -):$LD_LIBRARY_PATH"
fi

echo "Installing backend dependencies (this is fast if already installed)..."
pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
pip install --quiet -r backend/requirements.txt

# 2. Setup Frontend Environment
echo "Installing frontend dependencies..."
cd frontend
npm install --quiet
cd ..

echo "==================================================="
echo "🚀 Starting AeroPINN dev servers..."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173 (usually)"
echo "Press Ctrl+C to stop both servers."
echo "==================================================="

# 3. Start Processes in Background
python -m uvicorn backend.server.app:app --port 8000 &
BACKEND_PID=$!

cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# 4. Handle Cleanup on Exit
cleanup() {
    echo -e "\nShutting down servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "Done."
    exit 0
}

# Catch Ctrl+C (SIGINT) and termination signals
trap cleanup SIGINT SIGTERM

# Wait indefinitely for background processes
wait
