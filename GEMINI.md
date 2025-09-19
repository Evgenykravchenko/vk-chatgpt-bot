# Project Overview

This project is a VK bot that integrates with OpenAI's GPT models to provide an AI assistant in VK chats. The bot is built with Python and uses the `vk-api` library for interacting with the VK API and the `openai` library for generating AI responses.

The bot is designed to be scalable and maintainable, with a clear separation of concerns between data, business logic, and presentation layers. It uses a repository pattern for data access, a service layer for business logic, and handlers for processing incoming messages and commands.

**Key Features:**

*   **OpenAI Integration:** Supports GPT-3.5-turbo and GPT-4 models.
*   **Context Management:** Remembers the last N messages in a conversation.
*   **Request Limiting:** Controls the number of requests each user can make.
*   **Rate Limiting:** Protects the bot from spam.
*   **Admin Panel:** Allows administrators to manage users and settings.
*   **In-memory Storage:** Uses in-memory repositories for easy setup and development.

# Building and Running

To build and run the project, follow these steps:

1.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure environment variables:**

    Create a `.env` file in the root of the project and add the following variables:

    ```env
    VK_TOKEN=<your_vk_group_token>
    GROUP_ID=<your_vk_group_id>
    OPENAI_API_KEY=<your_openai_api_key>
    ADMIN_USER_ID=<your_vk_user_id>
    ```

3.  **Run the bot:**

    ```bash
    python main.py
    ```

# Development Conventions

*   **Code Style:** The project follows the PEP 8 style guide for Python code.
*   **Architecture:** The project uses a clean architecture with a repository pattern, service layer, and handlers.
*   **Data Access:** Data access is abstracted through repository interfaces, allowing for easy replacement of the data storage backend.
*   **Configuration:** Application settings are managed through a `Settings` class and loaded from environment variables.
*   **Error Handling:** The bot includes error handling for common issues such as API errors and rate limiting.
