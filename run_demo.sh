#!/bin/bash

# Ensure we are in the correct directory
cd "$(dirname "$0")"

# ==========================================
# 1. OLLAMA LOCAL HOST CONFIGURATION
# To use Ollama, uncomment the 3 lines below and comment out the NVIDIA section.
# ==========================================
 export OPENAI_API_KEY="ollama"  # OpenAI client requires some non-empty string
 export AGENT_BASE_URL="http://127.0.0.1:11434/v1"
 export AGENT_MODEL="gemma4b-agent:latest"     # Replace with your pulled model (e.g., mistral, phi3)


# Check if NVIDIA_API_KEY, OPENAI_API_KEY or OPENROUTER_API_KEY is set
if [ -z "$NVIDIA_API_KEY" ] && [ -z "$OPENAI_API_KEY" ] && [ -z "$OPENROUTER_API_KEY" ]; then
    echo "⚠️  No API key is set."
    echo "Please enter your API key (or press enter to skip):"
    read -rs API_KEY_INPUT
    
    if [ -n "$API_KEY_INPUT" ]; then
        export OPENAI_API_KEY="$API_KEY_INPUT"
    else
        echo "❌ Error: An API key is required to run the demo."
        exit 1
    fi
fi

echo "🚀 Running demo.py..."
python3 demo.py
