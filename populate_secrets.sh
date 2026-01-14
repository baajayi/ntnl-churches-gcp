#!/bin/bash
# Script to populate GCP Secret Manager secrets
# Usage: ./populate_secrets.sh

set -e  # Exit on error

PROJECT_ID="zeta-bonfire-476018-u6"

echo "Populating secrets for project: $PROJECT_ID"
echo "================================================"

# Function to add secret
add_secret() {
    local secret_name=$1
    local secret_value=$2

    if [ -z "$secret_value" ]; then
        echo "⚠️  Skipping $secret_name (empty value)"
        return
    fi

    echo -n "$secret_value" | gcloud secrets versions add "$secret_name" \
        --data-file=- \
        --project="$PROJECT_ID" 2>&1

    if [ $? -eq 0 ]; then
        echo "✅ Added secret: $secret_name"
    else
        echo "❌ Failed to add secret: $secret_name"
    fi
}

# Try to source .env file if it exists
if [ -f .env ]; then
    echo "Loading credentials from .env file..."
    source .env
fi

# Prompt for each secret if not set
echo ""
echo "Enter your API keys (press Enter to skip):"
echo "================================================"

# OpenAI API Key
if [ -z "$OPENAI_API_KEY" ]; then
    read -p "OpenAI API Key (sk-...): " OPENAI_API_KEY
fi
add_secret "OPENAI_API_KEY" "$OPENAI_API_KEY"

# Pinecone API Key
if [ -z "$PINECONE_API_KEY" ]; then
    read -p "Pinecone API Key (pcsk_...): " PINECONE_API_KEY
fi
add_secret "PINECONE_API_KEY" "$PINECONE_API_KEY"

# Discord Token
if [ -z "$DISCORD_TOKEN" ]; then
    read -p "Discord Bot Token: " DISCORD_TOKEN
fi
add_secret "DISCORD_TOKEN" "$DISCORD_TOKEN"

# Chatbot API Key
if [ -z "$CHATBOT_API_KEY" ]; then
    read -p "Chatbot API Key (or press Enter to skip): " CHATBOT_API_KEY
fi
if [ -n "$CHATBOT_API_KEY" ]; then
    add_secret "CHATBOT_API_KEY" "$CHATBOT_API_KEY"
else
    echo "⚠️  Skipped CHATBOT_API_KEY (optional)"
fi

echo ""
echo "================================================"
echo "✅ Secret population complete!"
echo ""
echo "Verify secrets:"
echo "gcloud secrets list --project=$PROJECT_ID"
