import discord
from discord.ext import commands
import requests
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHATBOT_API_URL = os.getenv('CHATBOT_API_URL')
CHATBOT_API_KEY = os.getenv('CHATBOT_API_KEY')

# Help message for when bot is mentioned without a question
HELP_MESSAGE = """Hello! I'm LutherBot. You can ask me questions in two ways:

1. **Using the prefix command:** `!ask <your question>`
2. **By mentioning me:** `@LutherBot <your question>`

Try asking me anything!"""

# Set up bot with command prefix
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')

def _make_api_request(question: str, user_id: str, channel_id: str):
    """
    Synchronous helper to make the actual HTTP request
    This runs in a thread pool to avoid blocking the event loop
    """
    # Prepare the API request
    headers = {
        'Content-Type': 'application/json',
    }

    # Add API key if available
    if CHATBOT_API_KEY:
        headers['Authorization'] = f'Bearer {CHATBOT_API_KEY}'

    # Prepare payload
    payload = {
        'query': question,
        'user_id': user_id,
        'channel_id': channel_id
    }

    # Send request to chatbot API
    response = requests.post(
        CHATBOT_API_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    return response

async def query_chatbot_api(question: str, user_id: str, channel_id: str):
    """
    Helper function to query the chatbot API
    Returns: tuple (success: bool, response: str)
    """
    try:
        # Run the blocking request in a thread pool to avoid blocking the event loop
        response = await asyncio.to_thread(_make_api_request, question, user_id, channel_id)

        # Check if request was successful
        if response.status_code == 200:
            data = response.json()
            # Extract answer from response
            answer = data.get('response') or data.get('answer') or data.get('message')
            return (True, answer)
        else:
            return (False, f"❌ Error: API returned status code {response.status_code}")

    except requests.exceptions.Timeout:
        return (False, "⏱️ Request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        return (False, f"❌ Error connecting to chatbot: {str(e)}")
    except Exception as e:
        return (False, f"❌ An error occurred: {str(e)}")

@bot.command(name='ask')
async def ask_chatbot(ctx, *, question: str):
    """
    Command: !ask <your question>
    Sends the question to your chatbot API and returns the response
    """
    # Show typing indicator while processing
    async with ctx.typing():
        # Call the helper function
        success, response = await query_chatbot_api(
            question,
            str(ctx.author.id),
            str(ctx.channel.id)
        )

        # Handle response chunking for Discord's 2000 character limit
        if len(response) > 2000:
            chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(response)

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if bot is mentioned
    if bot.user.mentioned_in(message):
        # Extract question by removing bot mention
        question = message.content
        for mention in message.mentions:
            if mention.id == bot.user.id:
                # Remove both <@ID> and <@!ID> formats (nickname mentions)
                question = question.replace(f'<@{mention.id}>', '').replace(f'<@!{mention.id}>', '').strip()

        # Handle empty question (just mention with no text)
        if not question:
            await message.channel.send(HELP_MESSAGE)
            return

        # Call API and send response
        async with message.channel.typing():
            success, response = await query_chatbot_api(
                question,
                str(message.author.id),
                str(message.channel.id)
            )

            # Handle chunking for long responses
            if len(response) > 2000:
                chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(response)

        # Return early to prevent command processing (avoids double responses)
        return

    # Process !ask commands normally
    await bot.process_commands(message)

# Run the bot
if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)