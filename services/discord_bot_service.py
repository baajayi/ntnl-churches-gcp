"""
Discord Bot Service - Background Thread Integration
Runs Discord bot as a daemon thread within the Flask application
"""

import threading
import discord
from discord.ext import commands
import requests
import os
import asyncio


class DiscordBotService:
    """Discord bot running as daemon thread in Flask app"""

    def __init__(self):
        self.bot = None
        self.thread = None
        self.token = os.getenv('DISCORD_TOKEN')
        self.api_url = os.getenv('CHATBOT_API_URL')
        self.api_key = os.getenv('CHATBOT_API_KEY')

        # Help message for when bot is mentioned without a question
        self.help_message = """Hello! I'm LutherBot. You can ask me questions in two ways:

1. **Using the prefix command:** `!ask <your question>`
2. **By mentioning me:** `@LutherBot <your question>`

Try asking me anything!"""

    def start(self):
        """Start Discord bot in background thread"""
        if not self.token:
            print("Discord bot disabled (DISCORD_TOKEN not set)")
            return

        if not self.api_url:
            print("Discord bot disabled (CHATBOT_API_URL not set)")
            return

        print("Starting Discord bot in background thread...")
        self.thread = threading.Thread(target=self._run_bot, daemon=True, name="DiscordBotThread")
        self.thread.start()
        print("Discord bot thread started")

    def _run_bot(self):
        """Run bot event loop in thread"""
        # Set up bot with command prefix
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix='!', intents=intents)

        # Store bot reference
        self.bot = bot

        @bot.event
        async def on_ready():
            print(f'{bot.user} has connected to Discord!')
            print(f'Bot is in {len(bot.guilds)} guilds')

        async def query_chatbot_api(question: str, user_id: str, channel_id: str):
            """
            Helper function to query the chatbot API
            Returns: tuple (success: bool, response: str)
            """
            try:
                # Prepare the API request
                headers = {
                    'Content-Type': 'application/json',
                }

                # Add API key if available
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'

                # Prepare payload
                payload = {
                    'query': question,
                    'user_id': user_id,
                    'channel_id': channel_id
                }

                # Run the blocking request in a thread pool
                response = await asyncio.to_thread(
                    requests.post,
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

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
                    await message.channel.send(self.help_message)
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
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bot.start(self.token))
        except Exception as e:
            print(f"Discord bot error: {e}")
        finally:
            print("Discord bot stopped")


# Singleton instance
_discord_bot_service = None


def get_discord_bot_service() -> DiscordBotService:
    """Get or create DiscordBotService singleton"""
    global _discord_bot_service
    if _discord_bot_service is None:
        _discord_bot_service = DiscordBotService()
    return _discord_bot_service
