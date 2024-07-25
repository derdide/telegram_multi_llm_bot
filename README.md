# telegram_multi_llm_bot
ChatBot to allow prompting of multiple LLMs in parallel, among other things

Configurable Models:
Set up environment variables for your API keys (TELEGRAM_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY).
Added OPENAI_MODEL and ANTHROPIC_MODEL to the environment variables.
These variables are used in the respective API calls, allowing easy model switching.

Multimodal Support [IT DOES NOT WORK YET]

Update your .env file with the new model variables.
Ensure you have the latest versions of the openai and anthropic libraries installed.
Run the updated bot script.

Users can:
Use /gpt or /claude commands with or without image attachments.
Use /compare command to get responses from both models, even for image-based queries.
Use /image command to use DALL-E 3 to generate images based on user prompts.
The generated image URL is sent back to the user in the Telegram chat.

Special Chat Modes [NOT TESTED YET]:
Through a chat-modes.json file, one can store different chat mode instructions.
Added a /mode command to switch between different chat modes.

API Usage Tracking:
Usea /balance command to display current API usage and costs. [CURRENT TRACKING IS WRONG]
