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

MAX_MESSAGE_LENGTH = 4096  # Telegram's maximum message length

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
    # Check if the table conversations exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
    if cursor.fetchone() is not None:
        # Table exists, check for columns
        cursor.execute("PRAGMA table_info(conversations)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add prompt_tokens if it doesn't exist
        if 'message' not in columns:
            cursor.execute("ALTER TABLE conversations ADD COLUMN message TEXT DEFAULT 0")
        
    else:
        # Table doesn't exist, create it with all necessary columns
            cursor.execute('''
               CREATE TABLE IF NOT EXISTS conversations
               (user_id INTEGER, message TEXT, response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
               ''')
 
    # Check if the table api_usage exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_usage'")
    if cursor.fetchone() is not None:
        # Table exists, check for columns
        cursor.execute("PRAGMA table_info(api_usage)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add prompt_tokens if it doesn't exist
        if 'prompt_tokens' not in columns:
            cursor.execute("ALTER TABLE api_usage ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
        
        # Add completion_tokens if it doesn't exist
        if 'completion_tokens' not in columns:
            cursor.execute("ALTER TABLE api_usage ADD COLUMN completion_tokens INTEGER DEFAULT 0")
        
        # Rename tokens_used to total_tokens if necessary
        if 'tokens_used' in columns and 'total_tokens' not in columns:
            cursor.execute("ALTER TABLE api_usage RENAME COLUMN tokens_used TO total_tokens")
        elif 'total_tokens' not in columns:
            cursor.execute("ALTER TABLE api_usage ADD COLUMN total_tokens INTEGER DEFAULT 0")
    else:
        # Table doesn't exist, create it with all necessary columns
        cursor.execute('''
        CREATE TABLE api_usage
        (api STRING, prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER, 
         cost REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
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
    /recent_usage - Check  
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

        # Log the full token usage
        logger.info(f"OpenAI API call - Prompt tokens: {response.usage.prompt_tokens}, "
                    f"Completion tokens: {response.usage.completion_tokens}, "
                    f"Total tokens: {response.usage.total_tokens}")

        # Track API usage
        tokens_used = response.usage.total_tokens
        save_api_usage("openai", 
                       response.usage.prompt_tokens, 
                       response.usage.completion_tokens, 
                       response.usage.total_tokens)


        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error in GPT request: {str(e)}")
        return "Error occurred while processing GPT request."

async def claude_request(prompt, image_content=None, mode=None):
    try:
        # Prepare messages for Claude API request
        message_content = prompt
        if mode and mode in CHAT_MODES:
            system_prompt = CHAT_MODES[mode]
            message_content = f"{system_prompt}\n\nHuman: {prompt}"
        
        if image_content:
            messages = [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_content}}
                ]}
            ]
        else:
            messages = [{"role": "user", "content": message_content}]

        logger.info(f"Sending request to Anthropic. Model: {ANTHROPIC_MODEL}, Messages: {messages}")

        # Make API call to Anthropic
        response = anthropic.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=int(ANTHROPIC_TOKENS),
            messages=messages
        )

        logger.info(f"Received response from Anthropic: {response}")

        # Calculate token usage
        prompt_tokens = len(message_content.split())
        completion_tokens = len(response.content[0].text.split())
        total_tokens = prompt_tokens + completion_tokens

        # Log the token usage
        logger.info(f"Anthropic API call - Prompt tokens (estimated): {prompt_tokens}, "
                    f"Completion tokens (estimated): {completion_tokens}, "
                    f"Total tokens (estimated): {total_tokens}")

        # Track API usage
        save_api_usage("anthropic", prompt_tokens, completion_tokens, total_tokens)

     
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error in Claude request: {str(e)}")
        return "Error occurred while processing Claude request."

async def split_long_message(message, max_length=4000):
    """
    Split a long message into multiple parts that fit within Telegram's message length limit.
    
    :param message: The message to split
    :param max_length: Maximum length of each part (default: 4000 to leave some room for formatting)
    :return: A list of message parts
    """
    if len(message) <= max_length:
        return [message]
    
    parts = []
    while len(message) > max_length:
        part = message[:max_length]
        last_newline = part.rfind('\n')
        if last_newline != -1:
            part = message[:last_newline]
            message = message[last_newline+1:]
        else:
            message = message[max_length:]
        parts.append(part)
    
    if message:
        parts.append(message)
    
    return parts

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, model_request, model_name, image_content = None, prompt = None):
    # Extract necessary information from the update object
    chat_id = update.effective_chat.id
    user_message = prompt if prompt is not None else update.message.text
    mode = context.user_data.get('mode')

    logger.info(f"Processing message for {model_name}. Chat ID: {chat_id}")
    logger.info(f"Message content: {user_message[:50]}...")  # Log first 50 chars of message
 
    # Check user authorization
    if not is_authorized(update):
        await context.bot.send_message(chat_id=chat_id, text="Sorry, you are not authorized to use this bot.")
        return

    # Process image content if present
    if image_content is None:
        logger.info("Checking for attached media")
        if update.message.document:
            logger.info(f"Document detected: {update.message.document.file_name}")
            try:
                file = await context.bot.get_file(update.message.document.file_id)
                image_content = await get_file_content(file)
                logger.info(f"Document processed for {model_name}. Size: {len(image_content)} bytes")
            except Exception as e:
                logger.error(f"Error processing document: {str(e)}")
        elif update.message.photo:
            logger.info(f"Photo detected. Number of sizes: {len(update.message.photo)}")
            try:
                file = await context.bot.get_file(update.message.photo[-1].file_id)
                image_content = await get_file_content(file)
                logger.info(f"Photo processed for {model_name}. Size: {len(image_content)} bytes")
            except Exception as e:
                logger.error(f"Error processing photo: {str(e)}")
        else:
            logger.info("No media detected in the message")
    else:
        logger.info("Image content already provided")

    # Request response from the specified AI model
    logger.info(f"Requesting response from {model_name}")
    response = await model_request(user_message, image_content, mode)
    logger.info(f"Received response from {model_name}. Length: {len(response)} characters")

    # Prepare the full response with the model name
    full_response = f"*{model_name} says:*\n\n{response}"
    
    # Manually split the response into parts to fit Telegram's message length limit
    response_parts = []
    while full_response:
        if len(full_response) <= MAX_MESSAGE_LENGTH:
            response_parts.append(full_response)
            break
        # Find the last newline character within the allowed length
        split_index = full_response.rfind('\n', 0, MAX_MESSAGE_LENGTH)
        if split_index == -1:  # If no newline found, split at the maximum length
            split_index = MAX_MESSAGE_LENGTH
        response_parts.append(full_response[:split_index])
        full_response = full_response[split_index:].lstrip()  # Remove leading whitespace from the next part
    
    total_parts = len(response_parts)
    logger.info(f"Response manually split into {total_parts} parts")

    # Inform the user if the response will be sent in multiple parts
    if total_parts > 1:
        await context.bot.send_message(chat_id=chat_id, text=f"Multi-part answer - expecting {total_parts} messages")

    # Send each part of the response
    for i, part in enumerate(response_parts, 1):
        try:
            logger.info(f"Sending part {i} of {total_parts}. Length: {len(part)} characters")
            await context.bot.send_message(
                chat_id=chat_id,
                text=escape_markdown(f"Part {i}/{total_parts}:\n\n{part}"),
                parse_mode='MarkdownV2'
            )
            logger.info(f"Successfully sent part {i} of {total_parts}")
            await asyncio.sleep(1)  # Add a small delay between messages to avoid rate limiting
        except Exception as e:
            logger.error(f"Error sending message part {i}: {str(e)}")
            try:
                # Fallback: try sending without markdown and escaping if the first attempt fails
                await context.bot.send_message(chat_id=chat_id, text=f"Part {i}/{total_parts}:\n\n{part}")
                logger.info(f"Sent part {i} without markdown")
            except Exception as e2:
                logger.error(f"Error sending plain message part {i}: {str(e2)}")

    # Save the conversation to the database
    save_to_database(update.effective_user.id, user_message, '\n'.join(response_parts))
    logger.info(f"Completed processing message for {model_name}")

    return '\n'.join(response_parts)


def escape_markdown(text):
    """Helper function to escape markdown special characters"""
    escape_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + char if char in escape_chars else char for char in text)

async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /gpt command
    logger.info("GPT command received")
    await update.message.reply_text("hold on a sec")
    await process_message(update, context, gpt_request, "GPT")

async def claude_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /claude command
    logger.info("Claude command received")
    await update.message.reply_text("hold on a sec")
    await process_message(update, context, claude_request, "Claude")

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Extract chat ID and inform the user that the request is being processed
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="Processing your request, please wait...")

    # Initialize image content as None
    image_content = None

    # Extract the user's message, removing the '/compare' command
    user_message = update.message.text.replace('/compare', '').strip()

    # Log the first 50 characters of the user's message for debugging
    logger.info(f"Received compare command. User message: {user_message[:50]}...")

    # Process attached document or photo, if any
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        image_content = await get_file_content(file)
        logger.info("Document received for comparison")
    elif update.message.photo:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_content = await get_file_content(file)
        logger.info("Photo received for comparison")

    # Process the message with Claude
    logger.info("Starting Claude response")
    claude_response = await process_message(update, context, claude_request, "Claude", image_content, prompt)
    logger.info(f"Completed Claude response. Length: {len(claude_response)} characters")

    # Add a delay between model responses to avoid rate limiting
    await asyncio.sleep(2)

    # Inform the user that GPT processing is starting
    await context.bot.send_message(chat_id=chat_id, text="Now processing GPT response")

    # Process the message with GPT
    logger.info("Starting GPT response")
    gpt_response = await process_message(update, context, gpt_request, "GPT", image_content, prompt)
    logger.info(f"Completed GPT response. Length: {len(gpt_response)} characters")

    # Inform the user that the comparison is complete
    await context.bot.send_message(chat_id=chat_id, text="Comparison complete.")
    logger.info("Comparison command completed")
 
async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    logger.info(f"Processing image generation request. Chat ID: {chat_id}")

    if not is_authorized(update):
        await context.bot.send_message(chat_id=chat_id, text="Sorry, you are not authorized to use this bot.")
        return

    prompt = user_message.replace('/generate_image', '').strip()
    if not prompt:
        await context.bot.send_message(chat_id=chat_id, text="Please provide a prompt for image generation.")
        return

    try:
        logger.info(f"Sending image generation request to OpenAI. Prompt: {prompt[:50]}...")
        
        response = openai.images.generate(
            model=IMAGE_GEN_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        logger.info(f"Image generated successfully. URL: {image_url}")

        # Estimate usage
        estimated_prompt_tokens = len(prompt.split())
        estimated_completion_tokens = 0
        estimated_total_tokens = estimated_prompt_tokens

        save_api_usage("openai_image", estimated_prompt_tokens, estimated_completion_tokens, estimated_total_tokens)
        logger.info(f"API usage saved for image generation. Estimated tokens: {estimated_total_tokens}")

        await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption="Generated image based on your prompt.")
        logger.info("Image sent to user successfully")

    except Exception as e:
        logger.error(f"Error in image generation: {str(e)}")
        error_message = "An error occurred while generating the image. Please try again later."
        await context.bot.send_message(chat_id=chat_id, text=error_message)

    logger.info(f"Completed processing image generation request for Chat ID: {chat_id}")

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
        await update.message.reply_text(f"Invalid mode. Available modes are: {available_modes}. Please use '/mode reset' to return to standard chat mode")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT api, SUM(prompt_tokens) as total_prompt_tokens, "
                   "SUM(completion_tokens) as total_completion_tokens, "
                   "SUM(total_tokens) as total_tokens FROM api_usage GROUP BY api")
    results = cursor.fetchall()
    conn.close()

    balance_text = "API Usage Summary:\n"
    for api, prompt_tokens, completion_tokens, total_tokens in results:
        balance_text += f"{api}:\n"
        balance_text += f"  Prompt Tokens: {prompt_tokens}\n"
        balance_text += f"  Completion Tokens: {completion_tokens}\n"
        balance_text += f"  Total Tokens: {total_tokens}\n\n"

    await update.message.reply_text(balance_text)

async def recent_usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute("SELECT api, prompt_tokens, completion_tokens, total_tokens, timestamp "
                   "FROM api_usage ORDER BY timestamp DESC LIMIT 10")
    results = cursor.fetchall()
    conn.close()

    usage_text = "Recent API Usage:\n"
    for api, prompt_tokens, completion_tokens, total_tokens, timestamp in results:
        usage_text += f"{timestamp} - {api}:\n"
        usage_text += f"  Prompt Tokens: {prompt_tokens}\n"
        usage_text += f"  Completion Tokens: {completion_tokens}\n"
        usage_text += f"  Total Tokens: {total_tokens}\n\n"

    await update.message.reply_text(usage_text)

def save_to_database(user_id, message, response):
    # Save conversation to SQLite database
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (user_id, message, response) VALUES (?, ?, ?)',
                   (user_id, message, response))
    conn.commit()
    conn.close()

def save_api_usage(api, prompt_tokens, completion_tokens, total_tokens):
    # Save API usage data to SQLite database
    conn = sqlite3.connect('bot_database.sqlite')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO api_usage (api, prompt_tokens, completion_tokens, total_tokens) VALUES (?, ?, ?, ?)',
                   (api, prompt_tokens, completion_tokens, total_tokens))
    conn.commit()
    conn.close()
    logger.info(f"API Usage saved: {api}, Prompt Tokens: {prompt_tokens}, "
                f"Completion Tokens: {completion_tokens}, Total Tokens: {total_tokens}")


def main():
    # Set up the database and initialize the Telegram bot
    setup_database()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("gpt", gpt_command))
    application.add_handler(CommandHandler("g", gpt_command))
    application.add_handler(CommandHandler("claude", claude_command))
    application.add_handler(CommandHandler("c", claude_command))
    application.add_handler(CommandHandler("compare", compare_command))
    application.add_handler(CommandHandler("both", compare_command))
    application.add_handler(CommandHandler("b", compare_command))
    application.add_handler(CommandHandler("image", generate_image_command))
    application.add_handler(CommandHandler("mode", set_mode_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("recent_usage", recent_usage_command))
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        lambda update, context: update.message.reply_text("Sorry, you are not authorized to use this bot.")
        if not is_authorized(update) else None
    ))
 
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
