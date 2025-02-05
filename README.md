# Multi-LLM Telegram Bot 🤖🚀

Welcome to the Multi-LLM Telegram Bot project! This versatile bot brings the power of GPT and Claude AI models directly to your Telegram chats, allowing to prompt both GPT and Claude through Telegram to easily compare the responses from both models. There are also  image generation capabilities and special chat modes.

I currently run this bot on a self-hosted Raspberry Pi running Raspbian. Most of the workload is on the LLM hosting side (e.g. OpenAI or Anthropic) and the resource useage on the bot side itself is quite low so far - of course, this may vary significantly depending on how many users run your bot. The bot is currently built with the assumption that usage will be limited with a low number of users (yourself, maybe friends and family).

## 🌟 Features

- **Dual AI Integration**: Interact with both GPT and Claude AI models. This is stateless so far, so each interaction is a one-off thing, there is no real "conversation" aspect
- **AI Comparison**: Compare responses from GPT and Claude side by side. Same comment about it being stateless.
- **Image Generation**: Create images on-the-fly using DALL-E.
- **Special Chat Modes**: Customize your AI interactions with predefined modes.
- ~**Image Understanding**: Send images to the AI models for analysis and discussion.~ This happens to not be as simple as expected, it remains planned - see issue #3 - and I don't want to take it out but it doesn't work at the moment
- **Usage Tracking**: Monitor your API usage - please take the results with a grain of salt (see issue #4)
- **Conversation History**: All interactions are saved for future reference. Feature is at level 0, interactions are stored, but there is no way to retrieve them and nothing is done with them (issue #5)

## 🛠️ Installation

0. **Prerequisites**

- Python 3.9 or higher
- A Telegram bot and its token (create one using [BotFather](https://core.telegram.org/bots#botfather))
- Your User ID (you can get it by sending a message to [userinfobot](https://t.me/userinfobot))
- A Telegram Group where your bot will be added - You'll need its ID too ([tuto](https://stackoverflow.com/questions/32423837/telegram-bot-how-to-get-a-group-chat-id))
- API keys for GPT and Claude

1. **Clone the repository**
   ```
   git clone https://github.com/derdide/telegram_multi_llm_bot/
   cd telegram_multi_llm_bot
   ```

2. **Set up a virtual environment** (optional but recommended)
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the project root and add the following:
   ```
   # Telegram settings
   TELEGRAM_TOKEN=your_telegram_token_here
   AUTHORIZED_USERS=your_telegram_user1,your_telegram_user2
   AUTHORIZED_GROUPS=your_telegram_group1,your_telegram_group2

   # Open AI settings
   OPENAI_API_KEY=your_openai_api_key_here
   OPENAI_MODEL=gpt-40-mini
   OPENAI_TOKENS=max_number_of_tokens_for_openai
   IMAGE_GEN_MODEL=dall-e-3

   # Anthropic settings
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ANTHROPIC_MODEL=claude-3-opus-20240229
   ANTHROPIC_TOKENS=max_number_of_tokens_for_anthropic_
   ```

5. **Set up the database**
   The bot will automatically create the necessary SQLite database when it first runs.

6. **Create a `chat-modes.json` file**
   This file should contain your custom chat modes. For example:
   ```json
   {
       "pro": "You are in a professional environment. I expect you to to be formal and straight to the point. No blah-blah",
       "creative": "You are expected to be creative and provide unconventional responses.",
       "french": "You are expected to always reply in French, even if the prompt is in English"
   }
   ```
## 🛸 Server
To setup the bot as a service on a Linux server (e.g. Raspberry Pi), please follow instructions here: https://github.com/derdide/telegram_multi_llm_bot/issues/11#issuecomment-2295244069

## 🚀 Usage

1. **Start the bot**
   ```
   python telegram-bot-main.py
   ```

2. **Interact with the bot on Telegram**
   - Start a chat with your bot on Telegram
   - Use the following commands:
     - `/start`: Get a welcome message and basic info
     - `/help`: View available commands
     - `/gpt <message>`: Interact with GPT
     - `/claude <message>`: Interact with Claude
     - `/compare <message>`: Compare responses from both Claude and GPT
     - `/image <prompt>`: Generate an image based on the prompt
     - `/mode <mode_name>`: Switch to a special chat mode. Use '/mode reset' to return back to standard chat mode
     - `/balance`: Check current API usage and costs

3. **Send images**

You can send images to the bot, and it will include them in the AI analysis

## 📊 API Usage and Costs

The bot tracks API usage for each interaction. Use the `/balance` command to view a summary of your usage.

## 🔐 Security Note

Keep your `.env` file secure and never share your API keys. The bot stores conversation history and API usage in a local SQLite database. Ensure you comply with data protection regulations if deploying this bot in a production environment.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- OpenAI for GPT and DALL-E APIs
- Anthropic for the Claude API
- The Python Telegram Bot library
- Claude itself (3.5 Sonnet model) for its (significant) technical assistance

---

Happy chatting with your AI-powered Telegram bot! If you have any questions or run into issues, please open an issue on GitHub. Enjoy exploring the capabilities of GPT and Claude through your Telegram chats! 🎉🤖
