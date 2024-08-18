# This script is designed to run with Python 3.9 or higher

import os
import logging
import asyncio
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
import openai
from anthropic import Anthropic
import base64
from dotenv import load_dotenv

# Set up logging for debugging and monitoring
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
 
# Load environment variables from a .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL')
OPENAI_TOKENS = os.getenv('OPENAI_TOKENS')
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL')
ANTHROPIC_TOKENS = os.getenv('ANTHROPIC_TOKENS')
IMAGE_GEN_MODEL = os.getenv('IMAGE_GEN_MODEL')

# Telegram authorized Users and group chats
def get_authorized_ids(env_var_name):
    ids_str = os.getenv(env_var_name, '')
    if not ids_str:
        return []
    return [int(id.strip()) for id in ids_str.split(',') if id.strip()]

AUTHORIZED_USERS = get_authorized_ids('AUTHORIZED_USERS')
AUTHORIZED_GROUPS = get_authorized_ids('AUTHORIZED_GROUPS')

def is_authorized(update: Update) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if AUTHORIZED_USERS and user_id in AUTHORIZED_USERS:
        return True
    if AUTHORIZED_GROUPS and chat_id in AUTHORIZED_GROUPS:
        return True
    return False
 
# Initialize API clients for OpenAI and Anthropic
openai.api_key = OPENAI_API_KEY
anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

# Load special chat modes from a JSON file
with open('chat-modes.json', 'r') as f:
    CHAT_MODES = json.load(f)

# Set up SQLite database for storing conversations and API usage
def setup_database():
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    # Create table for storing conversations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations
    (user_id INTEGER, message TEXT, response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    # Create table for tracking API usage
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_usage
    (api STRING, tokens_used INTEGER, cost REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Send welcome message when the command /start is issued
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    await update.message.reply_text('Welcome! I can help you interact with GPT and Claude, generate images, and use special chat modes. Use /help for more information.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Provide help information when the command /help is issued
    help_text = """
    Available commands:
    /gpt <message> - Interact with GPT
    /claude <message> - Interact with Claude
    /compare <message> - Compare responses from GPT and Claude
    /image <prompt> - Generate an image based on the prompt
    /mode <mode_name> - Switch to a special chat mode
    /balance - Check the current API usage and costs
    """
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    await update.message.reply_text(help_text)

async def get_file_content(file):
    # Download and encode file content as base64
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    file_content = await file.download_as_bytearray()
    return base64.b64encode(file_content).decode('utf-8')

async def gpt_request(prompt, image_content=None, mode=None):
    try:
        # Prepare messages for GPT API request
        messages = [{"role": "user", "content": prompt}]
        if mode and mode in CHAT_MODES:
            messages.insert(0, {"role": "system", "content": CHAT_MODES[mode]})
        if image_content:
            messages = [
             {"role": "user", "content": [
              {"type": "text", "text": prompt},
              {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}}
             ]}
            ]
        # adding some logging
        logger.info(f"Sending request to OpenAI. Model: {OPENAI_MODEL}, Messages: {messages}")

        # Make API call to OpenAI
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=int(OPENAI_TOKENS)
        )

        logger.info(f"Received response from OpenAI: {response}")

        # Track API usage
        tokens_used = response.usage.total_tokens
        cost = tokens_used * 0.00002  # Assuming $0.02 per 1K tokens, adjust as needed
        save_api_usage("openai", tokens_used, cost)

        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error in GPT request: {str(e)}")
        return "Error occurred while processing GPT request."

async def claude_request(prompt, image_content=None, mode=None):
    try:
        # Prepare messages for Claude API request
        messages = [{"role": "user", "content": prompt}]
        if mode and mode in CHAT_MODES:
            system_prompt = CHAT_MODES[mode]
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        if image_content:
            messages = [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_content}}
                ]}
            ]
        combined_prompt = ""
        if mode and mode in CHAT_MODES:
            combined_prompt += f"Human: {system_prompt}\n\nHuman: {prompt}\n\nAssistant:"
        else:
            combined_prompt += f"Human: {prompt}\n\nAssistant:"
        
        logger.info(f"Sending request to Anthropic. Model: {ANTHROPIC_MODEL}, Messages: {messages}")

        # Make API call to Anthropic
        response = anthropic.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=int(ANTHROPIC_TOKENS),
            messages=messages
        )

        logger.info(f"Received response from Anthropic: {response}")

        # Track API usage (Note: Anthropic doesn't provide token count, so we'll estimate)
        estimated_tokens = len(prompt.split()) + len(response.content[0].text.split())
        cost = estimated_tokens * 0.00002  # Adjust the cost calculation as needed
        save_api_usage("anthropic", estimated_tokens, cost)

        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in Claude request: {str(e)}")
        return "Error occurred while processing Claude request."

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, model_request):
    # Process user message and handle image attachments
    user_message = update.message.text
    image_content = None
    mode = context.user_data.get('mode')

    # adding some logging
    logger.info(f"Received message: {user_message}")
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        image_content = await get_file_content(file)
        logger.info("Document received and processed")
    elif update.message.photo:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_content = await get_file_content(file)
        logger.info("Photo received and processed")

    if image_content:
        logger.info("Image content successfully extracted")
    else:
        logger.info("No image content found")

    # Get response from the specified model
    response = await model_request(user_message, image_content, mode)
    await update.message.reply_text(response)
    save_to_database(update.effective_user.id, user_message, response)

def escape_markdown(text):
    """Helper function to escape markdown special characters"""
    escape_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + char if char in escape_chars else char for char in text)

async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /gpt command
    logger.info("GPT command received")
    await process_message(update, context, gpt_request)

async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /claude command
    logger.info("Claude command received")
    await process_message(update, context, claude_request)

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /compare command to get responses from both GPT and Claude
    user_message = update.message.text.replace('/compare', '').strip()
    image_content = None
    mode = context.user_data.get('mode')

    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        image_content = await get_file_content(file)
        logger.info("Document received for compare command")
    elif update.message.photo:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_content = await get_file_content(file)
        logger.info("Photo received for compare command")

    if image_content:
        logger.info("Image content successfully extracted for compare command")
    else:
        logger.info("No image content found for compare command")
    # Get responses from both models concurrently
    gpt_response, claude_response = await asyncio.gather(
        gpt_request(user_message, image_content, mode),
        claude_request(user_message, image_content, mode)
    )

    # Format the response using Telegram's markdown
    combined_response = (
        "*GPT Response:*\n"
        "\n"
        f"{escape_markdown(gpt_response)}\n"
        "\n\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\n"
        "*Claude Response:*\n"
        "\n"
        f"{escape_markdown(claude_response)}\n"
        ""
    )

    # Send the formatted message
    await update.message.reply_text(combined_response, parse_mode='MarkdownV2')
    save_to_database(update.effective_user.id, user_message, combined_response)

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /generate_image command to create images using DALL-E
    prompt = update.message.text.replace('/generate_image', '').strip()
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    if not prompt:
        await update.message.reply_text("Please provide a prompt for image generation.")
        return

    try:
        # Make API call to OpenAI for image generation
        response = openai.images.generate(
            model=IMAGE_GEN_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url

        # Estimate usage (since OpenAI doesn't provide token count for image generation)
        estimated_cost = 0.02  # Adjust based on your DALL-E API pricing
        save_api_usage("openai_image", 0, estimated_cost)

        await update.message.reply_photo(image_url, caption="Generated image based on your prompt.")
    except Exception as e:
        logger.error(f"Error in image generation: {str(e)}")
        await update.message.reply_text("An error occurred while generating the image.")

async def set_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /mode command to set special chat modes
    mode = context.args[0] if context.args else None
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    if mode == "reset":
        if 'mode' in context.user_data:
            del context.user_data['mode']
        await update.message.reply_text("Chat mode reset to normal.")
    elif mode and mode in CHAT_MODES:
        context.user_data['mode'] = mode
        await update.message.reply_text(f"Chat mode set to: {mode}")
    else:
        available_modes = ", ".join(CHAT_MODES.keys())
        await update.message.reply_text(f"Invalid mode. Available modes are: {available_modes}")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /balance command to show API usage summary
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT api, SUM(tokens_used) as total_tokens, SUM(cost) as total_cost FROM api_usage GROUP BY api")
    results = cursor.fetchall()
    conn.close()

    balance_text = "API Usage Summary:\n"
    for api, total_tokens, total_cost in results:
        balance_text += f"{api}: {total_tokens} tokens used, ${total_cost:.2f} spent\n"

    await update.message.reply_text(balance_text)

def save_to_database(user_id, message, response):
    # Save conversation to SQLite database
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (user_id, message, response) VALUES (?, ?, ?)',
                   (user_id, message, response))
    conn.commit()
    conn.close()

def save_api_usage(api, tokens_used, cost):
    # Save API usage data to SQLite database
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO api_usage (api, tokens_used, cost) VALUES (?, ?, ?)',
                   (api, tokens_used, cost))
    conn.commit()
    conn.close()

def main():
    # Set up the database and initialize the Telegram bot
    setup_database()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("claude", claude_command))
    application.add_handler(CommandHandler("compare", compare_command))
    application.add_handler(CommandHandler("image", generate_image_command))
    application.add_handler(CommandHandler("mode", set_mode_command))
    application.add_handler(CommandHandler("balance", balance_command))

    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        lambda update, context: update.message.reply_text("Sorry, you are not authorized to use this bot.")
        if not is_authorized(update) else None
    ))
 
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
