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

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
 
# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-vision-preview')
ANTHROPIC_MODEL = os.getenv('ANTHROPIC_MODEL', 'claude-3-opus-20240229')
IMAGE_GEN_MODEL = os.getenv('IMAGE_GEN_MODEL', 'dall-e-3')

# Initialize API clients
openai.api_key = OPENAI_API_KEY
anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)

# Load special chat modes
with open('chat-modes.json', 'r') as f:
    CHAT_MODES = json.load(f)

# Database setup
def setup_database():
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations
    (user_id INTEGER, message TEXT, response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS api_usage
    (api STRING, tokens_used INTEGER, cost REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
    ''')
    conn.commit()
    conn.close()

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Welcome! I can help you interact with GPT and Claude, generate images, and use special chat modes. Use /help for more information.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    Available commands:
    /gpt <message> - Interact with GPT
    /claude <message> - Interact with Claude
    /compare <message> - Compare responses from GPT and Claude
    /image <prompt> - Generate an image based on the prompt
    /mode <mode_name> - Switch to a special chat mode
    /balance - Check the current API usage and costs
    """
    await update.message.reply_text(help_text)

async def get_file_content(file):
    file_content = await file.download_as_bytearray()
    return base64.b64encode(file_content).decode('utf-8')

async def gpt_request(prompt, image_content=None, mode=None):
    try:
        messages = [{"role": "user", "content": prompt}]
        if mode:
            messages.insert(0, {"role": "system", "content": CHAT_MODES[mode]})
        if image_content:
            messages[-1]["content"] = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}}
            ]
        
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=300
        )
        
        # Track usage
        tokens_used = response.usage.total_tokens
        cost = tokens_used * 0.00002  # Assuming $0.02 per 1K tokens, adjust as needed
        save_api_usage("openai", tokens_used, cost)
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error in GPT request: {str(e)}")
        return "Error occurred while processing GPT request."

async def claude_request(prompt, image_content=None, mode=None):
    try:
        messages = [{"role": "user", "content": prompt}]
        if mode:
            messages.insert(0, {"role": "system", "content": CHAT_MODES[mode]})
        if image_content:
            messages[-1]["content"] = [
                {"type": "text", "text": prompt},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_content}}
            ]
        
        response = anthropic.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            messages=messages
        )
        
        # Track usage (Note: Anthropic doesn't provide token count, so we'll estimate)
        estimated_tokens = len(prompt.split()) + len(response.content[0].text.split())
        cost = estimated_tokens * 0.00002  # Adjust the cost calculation as needed
        save_api_usage("anthropic", estimated_tokens, cost)
        
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in Claude request: {str(e)}")
        return "Error occurred while processing Claude request."

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, model_request):
    user_message = update.message.text
    image_content = None
    mode = context.user_data.get('mode')

    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        image_content = await get_file_content(file)
    elif update.message.photo:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_content = await get_file_content(file)

    response = await model_request(user_message, image_content, mode)
    await update.message.reply_text(response)
    save_to_database(update.effective_user.id, user_message, response)

async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, gpt_request)

async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, claude_request)

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.replace('/compare', '').strip()
    image_content = None
    mode = context.user_data.get('mode')

    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        image_content = await get_file_content(file)
    elif update.message.photo:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_content = await get_file_content(file)

    gpt_response, claude_response = await asyncio.gather(
        gpt_request(user_message, image_content, mode),
        claude_request(user_message, image_content, mode)
    )

    combined_response = f"GPT Response:\n{gpt_response}\n\nClaude Response:\n{claude_response}"
    await update.message.reply_text(combined_response)
    save_to_database(update.effective_user.id, user_message, combined_response)

async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.replace('/generate_image', '').strip()
    if not prompt:
        await update.message.reply_text("Please provide a prompt for image generation.")
        return

    try:
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
    mode = context.args[0] if context.args else None
    if mode and mode in CHAT_MODES:
        context.user_data['mode'] = mode
        await update.message.reply_text(f"Chat mode set to: {mode}")
    else:
        available_modes = ", ".join(CHAT_MODES.keys())
        await update.message.reply_text(f"Invalid mode. Available modes are: {available_modes}")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (user_id, message, response) VALUES (?, ?, ?)',
                   (user_id, message, response))
    conn.commit()
    conn.close()

def save_api_usage(api, tokens_used, cost):
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO api_usage (api, tokens_used, cost) VALUES (?, ?, ?)',
                   (api, tokens_used, cost))
    conn.commit()
    conn.close()

def main():
    setup_database()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("claude", claude_command))
    application.add_handler(CommandHandler("compare", compare_command))
    application.add_handler(CommandHandler("image", generate_image_command))
    application.add_handler(CommandHandler("mode", set_mode_command))
    application.add_handler(CommandHandler("balance", balance_command))

    application.run_polling()

if __name__ == '__main__':
    main()
