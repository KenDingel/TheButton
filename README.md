# 🚨 THE BUTTON! 🚨

The Button Game is an interactive Discord bot that engages users in a collaborative game where they must keep a virtual button alive by clicking it before the timer runs out. The game encourages teamwork, strategy, and quick reflexes as players strive to maintain the button's life for as long as possible.

*Based on the Reddit April Fools event in 2015. https://en.wikipedia.org/wiki/The_Button_(Reddit)*

## Features
- Real-time button clicking game mechanics, utilizing Discord menu UI components
- Color-coded timer display with dynamic images, representing the button's health
- Role assignments based on click performance
- Leaderboard and player statistics tracking
- Customizable game settings (game timer duration, user cooldown duration)
- Automatic game session management for multiple concurrent games
- Efficient caching and database integration for optimal performance
- Rate limit management, due to the Discord API limitations

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/KenDingel/the-button-game.git
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up the database:
   - Create a MySQL database for the project.
   - Update the database configuration in `config.json` with your database credentials.

4. Configure the bot:
   - Create a new Discord bot application and obtain the bot token.
   - Update the `config.json` file with your bot token and other desired settings. (See below)

5. Run the bot:
   ```
   python button.py
   ```
   or running the bat script 'theButton.bat'

## Usage

1. Invite the bot to your Discord server using the provided invite link. This can be generated via the Discord Developer Portal (https://discord.com/developers/applications > Your Application > OAuth2 > Scopes: bot, Permissions: Send Messages, Read Message History, Add Reactions).

2. Start a new game session by running the command `startbutton` or `sb` in a designated game channel.

3. Players can click the button to reset the timer and keep the game going. The objective is to prevent the timer from reaching zero.

4. Players will earn color ranks based on their click performance, with each color representing a different tier of achievement.

5. Use commands like `myrank`, `leaderboard`, and `check` to view player statistics, leaderboard, and cooldown status.

6. The game ends when the timer reaches zero. An end-game summary will be displayed, showcasing the game duration, total clicks, most active participant, and other statistics.

Note this bot does not use a command prefix, so all commands are invoked directly without a prefix. Therefore, only give the bot permissions to the channels you want the game to be played in.

## Configuration

Inside assets/ create a new json file named 'config.json'. Copy the template below.
```
{
    "discord_token": "TOKEN HERE AS STRING",
    "sql_host": "sql_database_hostname.com",
    "sql_user": "button_admin",
    "sql_password": "password123",
    "sql_database": "thebutton",
    "sql_port": 3306,
    "timer_duration": 43200,
    "cooldown_duration": 3
}
```

## Acknowledgements

- [Nextcord](https://github.com/nextcord/nextcord) - A modern async ready API wrapper for Discord
- [MySQL Connector/Python](https://dev.mysql.com/doc/connector-python/en/) - A Python driver for communicating with MySQL servers.
- [Pillow](https://pillow.readthedocs.io/) - A Python Imaging Library for image processing.

## Contact

For any questions or inquiries, please contact the project owner:

- Name: Ken Dingel
- Email: DingelKen@gmail.com
- Discord: Regen2Moon
