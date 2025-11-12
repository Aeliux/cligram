Quick Start
===========

After installing cligram, you can quickly get started by following these steps:

1. **Create a Telegram application**

    - Visit the `Telegram API development tools <https://my.telegram.org/apps>`_ page.
    - Log in with your Telegram account.
    - Create a new application to obtain your **API ID** and **API Hash**.

2. **Set up your configuration file**

    - Create new configuration file:

      .. code-block:: bash

         cligram config create --global

    - Enter your **API ID** and **API Hash** when prompted.

3. **Add proxy settings (if needed)**

    - If you have network restrictions, you can configure one or more proxies:

      .. code-block:: bash

         cligram proxy add "<proxy_url>"

4. **Login to your Telegram account**

    - Run the following command to log in:

      .. code-block:: bash

         cligram session login

    - Follow the prompts to enter your phone number and the verification code sent to you by Telegram.

Congratulations! You are now ready to use cligram for automation and messaging tasks.
