#!/bin/bash

# ==============================================================================
# Setup Luma (Antigravity CLI) on Ubuntu VPS
# ==============================================================================

echo "========================================="
echo "   LUMA VPS SETUP & INITIALIZATION       "
echo "========================================="

# 1. Pastikan curl dipasang
if ! command -v curl &> /dev/null; then
    echo "[*] curl tidak dijumpai. Memasang curl..."
    sudo apt update && sudo apt install curl -y
fi

# 2. Install Antigravity CLI (agy)
if ! command -v agy &> /dev/null; then
    echo "[*] Memasang Antigravity CLI (agy)..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash
    
    # Masukkan PATH ke bashrc jika tiada
    if ! grep -q '\.local/bin' "$HOME/.bashrc"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[✓] Antigravity CLI (agy) sudah dipasang."
fi

# 3. Setup Global Rules untuk Luma (Step 6)
echo "[*] Membuat fail configurasi AGENTS.md untuk Luma..."
mkdir -p "$HOME/.gemini/config"
cat << 'EOF' > "$HOME/.gemini/config/AGENTS.md"
# Luma Rules
- Nama anda adalah Luma, coding assistant peribadi saya.
- Sila bercakap dalam campuran Bahasa Malaysia dan Bahasa Inggeris (rojak/santai).
- Anda bertugas untuk membantu saya menguruskan VPS dan membina/menambah tools dalam folder ~/projects/AURA-SDK.
EOF
echo "[✓] Fail ~/.gemini/config/AGENTS.md berjaya dibuat."

# 4. Setup tmux
if ! command -v tmux &> /dev/null; then
    echo "[*] tmux tidak dijumpai. Memasang tmux..."
    sudo apt update && sudo apt install tmux -y
fi

# 5. Start tmux session & run agy
echo "[*] Memulakan Luma di dalam tmux session 'luma'..."
if tmux has-session -t luma 2>/dev/null; then
    echo "[!] Session 'luma' sudah ada. Sila re-attach menggunakan: tmux a -t luma"
else
    echo "[*] Mencipta session tmux 'luma' dan memulakan agy..."
    echo "[!] NOTA: Sila lakukan Google Auth Login bila diarahkan nanti."
    echo ""
    # Jalankan tmux session baru dan jalankan agy secara terus
    tmux new-session -d -s luma 'export PATH="$HOME/.local/bin:$PATH"; agy'
    sleep 1
    tmux attach -t luma
fi
