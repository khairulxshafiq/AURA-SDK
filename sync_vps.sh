#!/bin/bash
echo "🔄 Memulakan sync data & memori AURA dari VPS..."
rsync -avz -e ssh \
  --exclude='.venv' \
  --exclude='__pycache__' \
  ubuntu@43.134.46.254:/home/ubuntu/projects/AURA-SDK/ /Users/khairulshafiq/Desktop/AURA-SDK/
echo "✅ Sync selesai! Memori & kod local PC kini 100% selari dengan VPS."
