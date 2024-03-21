import os
import json
import asyncio
import random
import datetime
from datetime import timezone
from io import BytesIO
import pytz
import logging
import traceback

import nextcord
from nextcord import File, Guild
from nextcord.ext import commands, tasks

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

from PIL import Image, ImageDraw, ImageFont

#set directory to where the script is located
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Logging
logging.basicConfig(filename='theButton.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load configuration from config.json
with open('config.json') as f:
    config = json.load(f)

db_pool = MySQLConnectionPool(
    pool_name="button_pool",
    pool_size=5,
    host=config['sql_host'],
    user=config['sql_user'],
    password=config['sql_password'],
    database=config['sql_database'],
    port=config['sql_port']
)

# Set up the MySQL connection
def get_db_connection():
    return db_pool.get_connection()

# Create a cursor object to interact with the database
db = get_db_connection()
cursor = db.cursor()

def reconnect_cursor():
    global db, cursor
    if not db.is_connected():
        global cursor
        db = get_db_connection()
        cursor = db.cursor()
        
# Create the necessary tables if they don't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS button_clicks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT,
        user_name VARCHAR(255),
        click_time DATETIME,
        timer_value INT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS latest_click (
        id INT AUTO_INCREMENT PRIMARY KEY,
        click_time DATETIME
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        cooldown_expiration DATETIME,
        color_rank VARCHAR(255),
        total_clicks INT DEFAULT 0,
        lowest_click_time INT,
        last_click_time DATETIME
    )
''')

db.commit()

# Set up the bot with the necessary intents
intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

lock = asyncio.Lock()

# Global variables
timer_value = config['timer_duration']
user_name, latest_click_time, start_time, total_clicks, last_timer_value, num_players = None, None, None, None, None, 0

# Define the color states
COLOR_STATES = [
    (255, 89, 94),    # 0-2 hours remaining (Red)
    (255, 146, 76),   # 2-4 hours remaining (Orange)
    (255, 202, 58),   # 4-6 hours remaining (Yellow)
    (138, 201, 38),   # 6-8 hours remaining (Green)
    (25, 130, 196),   # 8-10 hours remaining (Blue)
    (106, 76, 147)    # 10-12 hours remaining (Purple)
]

def get_color_state(timer_value):
    hours_remaining = int(timer_value) // 3600  # Ensure timer_value is int, just in case
    color_index = min(int(hours_remaining // 2), len(COLOR_STATES) - 1)  # Explicitly ensure integer
    return COLOR_STATES[color_index]

def get_color_emoji(timer_value):
    color = get_color_state(timer_value)
    if color == (255, 89, 94):  # Red
        return "🔴"
    elif color == (255, 146, 76):  # Orange
        return "🟠"
    elif color == (255, 202, 58):  # Yellow
        return "🟡"
    elif color == (138, 201, 38):  # Green
        return "🟢"
    elif color == (25, 130, 196):  # Blue
        return "🔵"
    elif color == (106, 76, 147):  # Purple
        return "🟣"

def generate_timer_image(timer_value):
    try:
        # Create a new image with the specified color state
        color = get_color_state(timer_value)
        image_width = 800
        image_height = 400
        image = Image.new('RGB', (image_width, image_height), color)

        # Draw the timer text on the image
        draw = ImageDraw.Draw(image)
        font_size = 120
        font = ImageFont.truetype('Mercy Christole.ttf', font_size)
        text = format_time(timer_value)
        # Formatted in H M S labeled format, with seconds formatted to 00 format 
        text = f"{format(int(timer_value//3600), '02d')}:{format(int(timer_value%3600//60), '02d')}:{format(int(timer_value%60), '02d')}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((image_width - text_width) // 2, (image_height - text_height) // 2 + 50)
        draw.text(position, text, font=font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Draw the additional text above the timer
        additional_text = "Time Left".upper()
        additional_font_size = 100
        additional_font = ImageFont.truetype('Mercy Christole.ttf', additional_font_size)
        additional_text_bbox = draw.textbbox((0, 0), additional_text, font=additional_font)
        additional_text_width = additional_text_bbox[2] - additional_text_bbox[0]
        additional_text_height = additional_text_bbox[3] - additional_text_bbox[1]
        additional_position = ((image_width - additional_text_width) // 2, 50, ((image_height - additional_text_height) // 2) - 200)
        draw.text(additional_position, additional_text, font=additional_font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Create a directory to save the timer images if it doesn't exist
        image_directory = 'timer_images'
        os.makedirs(image_directory, exist_ok=True)

        # Generate a unique filename based on the current timestamp
        image_filename = f'timer.png'
        image_path = os.path.join(image_directory, image_filename)

        # Save the image to a file in the specified directory
        image.save(image_path, 'PNG')

        # Return the image file path
        return image_path
    except Exception as e:
        tb = traceback.format_exc()
        print(f'Error generating timer image: {e}, {tb}')
        logger.error(f'Error generating timer image: {e}, {tb}')
        return None

def format_time(seconds):
    time = str(datetime.timedelta(seconds=seconds))
    return time

async def create_button_message():
    global button_message
    try:
        # Send the game explanation message
        explanation = (
            "🚨 THE BUTTON! 🚨\n"
            "Prepare yourselves for **The Button Game**\n"
            "A mysterious 12-hour countdown has begun, and the fate of the world rests in your hands! ⏰\n"
            "Keep the button alive and prevent the timer from reaching zero!\n"
            "You only get **1 click every 3 hours**. Choose wisely!\n\n"
            "The button color represents the remaining time:\n"
            "- 🔴 Red: 0-2 hrs (Danger Zone!)\n"
            "- 🟠 Orange: 2-4 hrs (Getting Risky!)\n"
            "- 🟡 Yellow: 4-6 hrs (Caution Advised!)\n"
            "- 🟢 Green: 6-8 hrs (Safe... For Now!)\n"
            "- 🔵 Blue: 8-10 hrs (Steady Progress!)\n"
            "- 🟣 Purple: 10-12 hrs (Nicely Done!)\n\n"
            "As a reward for your bravery, you'll earn the colored circle of the time you clicked!\n"
            "Use `myrank` to check your personal stats and `leaderboard` to see how you stack up against other fearless clickers!\nUse 'check' to see if you have a click ready for action! \n\n"
            "Do you have what it takes to keep the button alive and prevent the timer from reaching zero?\n\n"
            "*Based on the Reddit April Fools event in 2015. https://en.wikipedia.org/wiki/The_Button_(Reddit)*"
        )
        await bot.get_channel(config['button_channel_id']).send(explanation)

        # Create the button message
        embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='Click the button to start the game!')
        message = await bot.get_channel(config['button_channel_id']).send(embed=embed, view=ButtonView(config['timer_duration']))
        config['button_message_id'] = message.id
        button_channel = bot.get_channel(config['button_channel_id'])
        button_message = await button_channel.fetch_message(config['button_message_id'])

        # Save the updated config to config.json
        with open('config.json', 'w') as f:
            json.dump(config, f)

        # Create the color roles if they don't exist
        guild = bot.get_guild(config['guild_id'])
        for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
            role = nextcord.utils.get(guild.roles, name=color_name)
            if role is None:
                role = await guild.create_role(name=color_name, color=nextcord.Color.from_rgb(*color_value))
            else:
                await role.edit(color=nextcord.Color.from_rgb(*color_value))
                
        # Update the button message embed description
        embed.description = '**The game has started! Keep the button alive!**'
        await message.edit(embed=embed)
    except Exception as e:
        tb = traceback.format_exc()
        print(f'Error creating button message: {e}, {tb}')
        logger.error(f'Error creating button message: {e}, {tb}')

prev_timer_val = None
timer_loop_count = 0

@tasks.loop(seconds=5)
async def update_timer():
    global button_message, user_name, latest_click_time, start_time, total_clicks, last_timer_value, timer_value, prev_timer_val, num_players
    global timer_loop_count
    global cursor, db
        
    try:
        if latest_click_time is None: #(datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds() >= 900:
            # Reconnect to the database if the connection is lost
            reconnect_cursor()
            
            cursor.execute('''
                SELECT user_name, click_time, (SELECT MIN(click_time) FROM button_clicks) AS start_time, 
                    (SELECT COUNT(*) FROM button_clicks) AS total_clicks, timer_value
                FROM button_clicks
                ORDER BY id DESC
                LIMIT 1
            ''')
            result = cursor.fetchone()

            if result:
                user_name, latest_click_time, start_time, total_clicks, last_timer_value = result
                latest_click_time = latest_click_time.replace(tzinfo=timezone.utc) if latest_click_time.tzinfo is None else latest_click_time
                elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds()
                timer_value = int(max(config['timer_duration'] - elapsed_time, 0))

                if start_time:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                    elapsed_time = (datetime.datetime.now(timezone.utc) - start_time).total_seconds()
                    
                    # Count the number of rows in the users table to find the number of players. SQL Explanation: COUNT(*) returns the number of rows in the table
                    cursor.execute('SELECT COUNT(*) FROM users')
                    num_players = cursor.fetchone()[0]
                else:
                    logging.error('Start time is None')
                    return
            else:
                logging.error('Latest click time is None, game not started yet.')
                return
        else:
            # All the data is already available, no need to query the database
            '''logging.info('All the data is already available, no need to query the database')
            logging.info(f'Latest click time: {latest_click_time}')
            logging.info(f'Start time: {start_time}')
            logging.info(f'Total clicks: {total_clicks}')
            logging.info(f'Last timer value: {last_timer_value}')'''
            elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds()
            timer_value = max(config['timer_duration'] - elapsed_time, 0)
            logging.info(f'Timer value: {timer_value}')
            # print(f"Timer value: {timer_value}")
            
        # Prevent the timer from skipping by more than 5 minutes, use previous timer value if it does so
        if prev_timer_val is not None and abs(timer_value - prev_timer_val) > 300:
            timer_value = prev_timer_val
            logging.info(f'Prevented timer from skipping, using previous timer value: {timer_value}')
        prev_timer_val = timer_value
        
        # Get color state and format latest click time for display
        color_state = get_color_state(last_timer_value)
        color_index = COLOR_STATES.index(color_state)
        color_name = ["Red", "Orange", "Yellow", "Green", "Blue", "Purple"][color_index]
        emoji = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣"][color_index]
        
        current_color_state = get_color_state(timer_value)
        current_color_index = COLOR_STATES.index(current_color_state)
        current_color_name = ["Red", "Orange", "Yellow", "Green", "Blue", "Purple"][current_color_index]
        current_emoji = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣"][current_color_index]
        
        formatted_time = f'<t:{int(latest_click_time.timestamp())}:R>'
        time_value_formatted = format_time(timer_value)
        latest_user_info = f'{formatted_time} {user_name} clicked at  {emoji} {color_name}.'    
        
        # See if variable for button message is set and working by testing if can retrieve the message
        try:
            button_message_text = button_message.content
        except Exception as e:
            logging.error(f'Error retrieving button message: {e}')
            button_message = None
            try:
                button_channel = bot.get_channel(config['button_channel_id'])
                button_message = await button_channel.fetch_message(config['button_message_id'])
            except nextcord.NotFound:
                logging.error('Button message not found, creating a new button message...')
                await create_button_message()
                button_channel = bot.get_channel(config['button_channel_id'])
                button_message = await button_channel.fetch_message(config['button_message_id'])
            except Exception as e:
                logging.error(f'Error fetching button message: {e}')
                return
        
        embed = button_message.embeds[0]
        
        if timer_value <= 0:
            # Timer has reached zero, end the game
            embed = nextcord.Embed(title='The Button Game', description='Game Ended!')

            # Retrieve and add overall game stats to the embed
            cursor.execute('SELECT COUNT(*) FROM button_clicks')
            total_clicks = cursor.fetchone()[0]
            embed.add_field(name='Total Button Clicks', value=str(total_clicks), inline=False)

            cursor.execute('SELECT MIN(click_time), MAX(click_time) FROM button_clicks')
            start_time, end_time = cursor.fetchone()
            duration = end_time - start_time
            embed.add_field(name='Game Duration', value=str(duration), inline=False)

            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM button_clicks')
            num_participants = cursor.fetchone()[0]
            embed.add_field(name='Number of Participants', value=str(num_participants), inline=False)

            cursor.execute('SELECT user_name, COUNT(*) AS click_count FROM button_clicks GROUP BY user_id ORDER BY click_count DESC LIMIT 1')
            most_active = cursor.fetchone()
            embed.add_field(name='Most Active Participant', value=f"{most_active[0]} ({most_active[1]} clicks)", inline=False)

            cursor.execute('SELECT MAX(timer_value) FROM button_clicks')
            longest_timer = cursor.fetchone()[0]
            embed.add_field(name='Longest Timer Reached', value=format_time(longest_timer), inline=False)

            color_distribution = []
            for color in ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple']:
                role = nextcord.utils.get(Guild.roles, name=color)
                count = len(role.members)
                color_distribution.append(f"- {color}: {count}")
            embed.add_field(name='Color Click Distribution', value='\n'.join(color_distribution), inline=False)
            update_timer.stop()
            logging.info('Game Ended!')
        else:
            embed.clear_fields()
            embed.add_field(name='👤 Latest Click', value=latest_user_info, inline=False)
        
            # Calculate and display how long the game has been running
            # Game Started variable of 2024 03 17 12:59:55 UTC
            start_time = datetime.datetime(2024, 3, 17, 12, 59, 55, tzinfo=timezone.utc)
            elapsed_time = datetime.datetime.now(timezone.utc) - start_time
            # Estimate the time the game has been running in days, hours, minutes, and seconds
            elapsed_days = elapsed_time.days
            elapsed_hours = elapsed_time.seconds // 3600
            elapsed_minutes = (elapsed_time.seconds % 3600) // 60
            elapsed_seconds = elapsed_time.seconds % 60
            elapsed_time_str = f'{elapsed_days} days, {elapsed_hours} hours, {elapsed_minutes} minutes, {elapsed_seconds} seconds'
            total_clicks_msg = f'{total_clicks} clicks'
            total_players_msg = f'{num_players}'
            # Description area with message of all stats msgs/str concatenated in an adventure game toned wording! Calling players knights or adventurers
            embed.description = f'The game ends when the timer hits 0.\nClick the button to reset it and keep the game going!\n\nValiant clickers, you have kept the button alive for {elapsed_time_str}! In your pursuit of glory, {total_clicks_msg} have been made by {total_players_msg} adventurers! 🛡️🗡️🏰\n\nWill you join the ranks of the brave and keep the button alive?'
            embed.set_footer(text=f'The Button Game by Regen2Moon; Inspired by Josh Wardle')
            
            # Generate the timer image and set it as the embed image
            timer_image_path = generate_timer_image(timer_value)
            embed.set_image(url=f'attachment://{os.path.basename(timer_image_path)}')

            pastel_color = get_color_state(timer_value)
            embed.color = nextcord.Color.from_rgb(*pastel_color)

            button_view = ButtonView(timer_value)
            await button_message.edit(embed=embed, file=nextcord.File(timer_image_path), view=button_view)
    except Exception as e:
        tb = traceback.format_exc()
        print(f'Error updating timer: {e}, {tb}')
        logger.error(f'Error updating timer: {e}, {tb}')
        
class CooldownManager:
    def __init__(self):
        self.db_config = config
        self.add_initial_user_data()
        
    def add_initial_user_data(self):
        reconnect_cursor()
        global cursor, db

        cursor.execute('''
            INSERT INTO users (user_id, cooldown_expiration, total_clicks, lowest_click_time, last_click_time)
            SELECT user_id, 
                CASE
                    WHEN DATE_ADD(MAX(click_time), INTERVAL 3 HOUR) > UTC_TIMESTAMP() THEN DATE_ADD(MAX(click_time), INTERVAL 3 HOUR)
                    ELSE NULL
                END AS cooldown_expiration,
                COUNT(*) AS total_clicks,
                MIN(timer_value) AS lowest_click_time,
                MAX(click_time) AS last_click_time
            FROM button_clicks
            WHERE click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 HOUR)
            GROUP BY user_id
            ON DUPLICATE KEY UPDATE
                cooldown_expiration = VALUES(cooldown_expiration),
                total_clicks = VALUES(total_clicks),
                lowest_click_time = VALUES(lowest_click_time),
                last_click_time = VALUES(last_click_time)
        ''')
        # Additional logic to update cooldown_expiration for existing records
        cursor.execute('''
            UPDATE users
            SET cooldown_expiration = NULL
            WHERE cooldown_expiration IS NOT NULL AND cooldown_expiration < UTC_TIMESTAMP()
        ''')
        db.commit()


    def add_or_update_user(self, user_id, cooldown_duration, color_rank, timer_value):
        reconnect_cursor()
        global cursor, db
        cooldown_expiration = datetime.datetime.now(timezone.utc) + cooldown_duration
        cursor.execute('''
            INSERT INTO users (user_id, cooldown_expiration, color_rank, total_clicks, lowest_click_time, last_click_time)
            VALUES (%s, %s, %s, 1, %s, %s)
            ON DUPLICATE KEY UPDATE
                cooldown_expiration = VALUES(cooldown_expiration),
                color_rank = VALUES(color_rank),
                total_clicks = total_clicks + 1,
                lowest_click_time = LEAST(lowest_click_time, VALUES(lowest_click_time)),
                last_click_time = VALUES(last_click_time)
        ''', (user_id, cooldown_expiration, color_rank, timer_value, datetime.datetime.now(timezone.utc)))
        db.commit()

    def remove_expired_cooldowns(self):
        reconnect_cursor()
        global cursor, db
        cursor.execute('UPDATE users SET cooldown_expiration = NULL WHERE cooldown_expiration <= %s', (datetime.datetime.now(timezone.utc),))
        db.commit()

cooldown_manager = CooldownManager()

class ButtonView(nextcord.ui.View):
    def __init__(self, timer_value): #, user_id: int = None):
        super().__init__(timeout=None)  # Set timeout=None if you want the buttons to be always active
        self.timer_value = timer_value
        #self.user_id = user_id
        self.add_button()

    def add_button(self):
        button_label = "Click me!"

        color = get_color_state(self.timer_value)
        style = nextcord.ButtonStyle.gray
        if color == (255, 89, 94):  # Red
            style = nextcord.ButtonStyle.danger
        elif color == (255, 146, 76):  # Orange
            style = nextcord.ButtonStyle.secondary
        elif color == (255, 202, 58):  # Yellow
            style = nextcord.ButtonStyle.secondary
        elif color == (138, 201, 38):  # Green
            style = nextcord.ButtonStyle.success
        elif color == (25, 130, 196):  # Blue
            style = nextcord.ButtonStyle.primary
        elif color == (106, 76, 147):  # Purple
            style = nextcord.ButtonStyle.primary

        self.clear_items()
        button = TimerButton(style=style, label=button_label, timer_value=self.timer_value)
        self.add_item(button)

class TimerButton(nextcord.ui.Button):
    def __init__(self, style, label, timer_value):
        super().__init__(style=style, label=label, custom_id="dynamic_button")
        self.timer_value = timer_value  # Store timer_value if needed

    def update_button_color(self):
        color = get_color_state(self.timer_value)
        style = nextcord.ButtonStyle.gray
        if color == (255, 89, 94):  # Red
            style = nextcord.ButtonStyle.danger
        elif color == (255, 146, 76):  # Orange
            style = nextcord.ButtonStyle.secondary
        elif color == (255, 202, 58):  # Yellow
            style = nextcord.ButtonStyle.secondary
        elif color == (138, 201, 38):  # Green
            style = nextcord.ButtonStyle.success
        elif color == (25, 130, 196):  # Blue
            style = nextcord.ButtonStyle.primary
        elif color == (106, 76, 147):  # Purple
            style = nextcord.ButtonStyle.primary
        self.style = style
        
    async def callback(self, interaction: nextcord.Interaction):
        await lock.acquire()
        try:
            await interaction.response.defer(ephemeral=True)
            print(f'Button clicked by {interaction.user}!')
            logger.info(f'Button clicked by {interaction.user}!')
        except Exception as e:
            print(f'Error processing button click: {e}')
            logger.error(f'Error processing button click: {e}')
            pass
        
        try:
            print(f'Button clicked by {interaction.user}!')
            logger.info(f'Button clicked by {interaction.user}!')
            button_channel = bot.get_channel(config['button_channel_id'])
            button_message = await button_channel.fetch_message(config['button_message_id'])

            embed = button_message.embeds[0]

            # if cursor is not connected
            global cursor, db
            reconnect_cursor()
            
            cursor.execute('''
                SELECT MAX(click_time) AS latest_click_time,
                    COUNT(*) AS click_count,
                    MAX(IF(user_id = %s, click_time, NULL)) AS last_click_time
                FROM button_clicks
                WHERE click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 HOUR)
            ''', (interaction.user.id,))
            
            result = cursor.fetchone()
            
            noclicks = False
            # if result is None, then the user has not clicked the button in the last 3 hours. So sql again to get the latest click time and click count and if there is no click from the user then grab the last click of any user.
            if result[0] is None:
                cursor.execute('''
                    SELECT MAX(click_time) AS latest_click_time,
                        COUNT(*) AS click_count,
                        MAX(click_time) AS last_click_time
                    FROM button_clicks
                ''')
                result = cursor.fetchone()
                noclicks = True
            
            click_count = result[1]
            
            latest_click_time = result[0]
            latest_click_time = latest_click_time.replace(tzinfo=timezone.utc)
            elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds()
            current_timer_value = max(config['timer_duration'] - elapsed_time, 0)

            if current_timer_value <= 0:
                await interaction.followup.send("The game has already ended!", ephemeral=True)
                lock.release() 
                return
            
            last_click_time = result[2]
            
            #print all the data
            print(f'latest_click_time: {latest_click_time}', f'elapsed_time: {elapsed_time}', f'current_timer_value: {current_timer_value}', f'click_count: {click_count}', f'last_click_time: {last_click_time}')
            try:
                if not noclicks and click_count >= 1 and last_click_time is not None:
                    last_click_time = last_click_time.replace(tzinfo=timezone.utc)
                    cooldown_remaining = (last_click_time + datetime.timedelta(hours=3)) - datetime.datetime.now(timezone.utc)
                    cooldown_remaining = int(cooldown_remaining.total_seconds())
                    formatted_cooldown  = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                    await interaction.followup.send(f'You have already clicked the button in the last 3 hours. Please try again in {formatted_cooldown}', ephemeral=True)
                    print(f'User {interaction.user} is on cooldown for {formatted_cooldown}')
                    logger.info(f'User {interaction.user} is on cooldown for {formatted_cooldown}')
                    lock.release()
                    return
            except Exception as e:
                tb = traceback.format_exc()
                print(f'Error processing button click: {e}, {tb}')
                logger.error(f'Error processing button click: {e}, {tb}')
                #await interaction.followup.send("An error occurred while processing the button click.", ephemeral=True)
                lock.release()
            
            # cursor.execute('''
            #     SELECT COALESCE(MAX(click_time), UTC_TIMESTAMP() - INTERVAL %s SECOND) AS  latest_click_time,
            #     COUNT(*) AS click_count,
            #     MAX(click_time) AS last_click_time
            #     FROM button_clicks
            # ''', (config['timer_duration']))cur
            color_state = get_color_state(current_timer_value)

            embed.clear_fields()
            embed.add_field(name='Time remaining', value=format_time(current_timer_value))

            timer_image_path = generate_timer_image(current_timer_value)
            embed.set_image(url=f'attachment://{os.path.basename(timer_image_path)}')

            await button_message.edit(embed=embed, file=nextcord.File(timer_image_path))

            cursor.execute('INSERT INTO button_clicks (user_id, user_name, click_time, timer_value) VALUES (%s, %s, %s, %s)', (interaction.user.id, str(interaction.user), datetime.datetime.now(timezone.utc), current_timer_value))
            cursor.execute('INSERT INTO latest_click (click_time) VALUES (%s)', (datetime.datetime.now(timezone.utc),))
            db.commit()
            print(f'Data inserted for {interaction.user}!')
            logger.info(f'Data inserted for {interaction.user}!')

            guild = interaction.guild
            role_name = None
            for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
                if color_state == color_value:
                    role_name = color_name
                    break

            if role_name:
                role = nextcord.utils.get(guild.roles, name=role_name)
                if role:
                    await interaction.user.add_roles(role)

            self.update_button_color()
            await interaction.followup.send("Button clicked! You have earned a " + role_name + " click!", ephemeral=True)
            
            cooldown_duration = datetime.timedelta(hours=3)
            color_rank = role_name
            cooldown_manager.add_or_update_user(interaction.user.id, cooldown_duration, color_rank, current_timer_value)
            
            color_emoji = get_color_emoji(current_timer_value)
            # remaining_time = format_time(current_timer_value)
            # Formatted in H M S labeled format
            formatted_remaining_time = f"{format(int(current_timer_value//3600), '02d')} hours {format(int(current_timer_value%3600//60), '02d')} minutes and {format(int(current_timer_value%60), '02d')} seconds"
            embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {role_name} rank!", color=nextcord.Color.from_rgb(*color_state))
            chat_channel = bot.get_channel(config['chat_channel_id'])
            display_name = interaction.user.display_name
            if not display_name:
                display_name = interaction.user.name
            embed.description = f"{color_emoji}! {display_name} ({interaction.user.mention}), the {role_name} rank warrior, has valiantly reset the timer with a mere {formatted_remaining_time} remaining! Let their bravery be celebrated throughout the realm!"
            await chat_channel.send(embed=embed)
            
            # Set the cooldown for the user
            cooldown_manager.add_or_update_user(interaction.user.id, datetime.timedelta(hours=3), role_name, current_timer_value)
            if not update_timer.is_running():
                update_timer.start()
            lock.release()
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error processing button click: {e}, {tb}')
            logger.error(f'Error processing button click: {e}, {tb}')
            await interaction.followup.send("An error occurred while processing the button click.", ephemeral=True)
            lock.release()

@bot.event
async def on_message(message):
    global cursor, db
    if message.author == bot.user and message.content.lower() != "sb": return
    if message.channel.id != config['button_channel_id'] and message.channel.id != config['chat_channel_id']: return

    await lock.acquire()
    reconnect_cursor()
    
    if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
        # purge channel
        await message.channel.purge(limit=100, check=lambda m: m.author == bot.user)
        if message.author.guild_permissions.administrator:
            await create_button_message()
            #await message.channel.send('Button game started!')
        else:
            await message.channel.send('You do not have permission to start the button game.')
        try:
            await message.delete()
        except:
            pass
        if not update_timer.is_running():
            update_timer.start()

    elif message.content.lower() == 'myrank':
        is_other_user = False
        if len(message.content.split(" ")) > 1:
            user_check_id = int(message.content.split(" ")[1][3:-1])
            is_other_user = True
        else:
            user_check_id = message.author.id
            
        try:
            cursor.execute('''
                SELECT
                    timer_value,
                    click_time
                FROM button_clicks
                WHERE user_id = %s
                ORDER BY click_time
            ''', (user_check_id,))
            
            clicks = cursor.fetchall()
            
            def Counter(emojis):
                counts = {}
                for emoji in emojis:
                    if emoji in counts:
                        counts[emoji] += 1
                    else:
                        counts[emoji] = 1
                return counts
            
            if clicks:
                color_emojis = [get_color_emoji(timer_value) for timer_value, _ in clicks]
                color_counts = Counter(color_emojis)
                
                total_claimed_time = sum(config['timer_duration'] - timer_value for timer_value, _ in clicks)
                
                emoji_sequence = ' '.join(color_emojis)
                color_summary = ', '.join(f'{emoji} x{count}' for emoji, count in color_counts.items())
                
                if not is_other_user:
                    user_check_name = message.author.display_name if message.author.display_name else message.author.name
                    embed = nextcord.Embed(
                        title='Your Heroic Journey',
                        description=f"Behold, brave {user_check_name}, the chronicle of your valiant clicks!\n\n"
                                    f'Click History: {emoji_sequence}\n\n'
                                    f'Color Summary: {color_summary}\n\n'
                                    f'Total Time Claimed: {format_time(total_claimed_time)}\n\n'
                                    "Your unwavering dedication to the button shall be remembered in the annals of history!"
                    )
                else:
                    user = await bot.fetch_user(user_check_id)
                    user_check_name = user.display_name if user.display_name else user.name
                    embed = nextcord.Embed(
                        title='Heroic Journey of Another',
                        description=f"Behold, brave {user_check_name}, the chronicle of their valiant clicks!\n\n"
                                    f'Click History: {emoji_sequence}\n\n'
                                    f'Color Summary: {color_summary}\n\n'
                                    f'Total Time Claimed: {format_time(total_claimed_time)}\n\n'
                                    "Their unwavering dedication to the button shall be remembered in the annals of history!"
                    )
                await message.channel.send(embed=embed)
            else:
                if not is_other_user:
                    await message.channel.send('Alas, noble warrior, your journey has yet to begin. Step forth and make your mark upon the button!')
                else:
                    await message.channel.send('Alas, noble warrior, their journey has yet to begin. Step forth and make your mark upon the button!')
        
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving user rank: {e}, {tb}')
            logger.error(f'Error retrieving user rank: {e}, {tb}')
            if not is_other_user:
                await message.channel.send('An error occurred while retrieving your rank. The button spirits are displeased!')
            else:
                await message.channel.send('An error occurred while retrieving the user rank. The button spirits are displeased!')
    
    elif message.content.lower() in ['leaderboard', 'scores', 'scoreboard', 'top']:
    # Set the default number of entries to display for each category
        num_entries = 5

        # Check if the user provided a custom number of entries
        if len(message.content.split()) > 1:
            try:
                num_entries = int(message.content.split()[1])
            except ValueError:
                pass  # If the provided value is not an integer, use the default value

        try:
            cursor.execute('''
                SELECT 
                    user_name,
                    COUNT(*) AS total_clicks,
                    GROUP_CONCAT(
                        CASE
                            WHEN timer_value >= 36000 THEN '🟣'
                            WHEN timer_value >= 28800 THEN '🔵'
                            WHEN timer_value >= 21600 THEN '🟢'
                            WHEN timer_value >= 14400 THEN '🟡'
                            WHEN timer_value >= 7200 THEN '🟠'
                            ELSE '🔴'
                        END
                        ORDER BY timer_value
                        SEPARATOR ''
                    ) AS color_sequence
                FROM button_clicks
                GROUP BY user_id
                ORDER BY total_clicks DESC
                LIMIT 10
            ''')
            most_clicks = cursor.fetchall()

            cursor.execute('''
                SELECT user_name, timer_value
                FROM button_clicks
                ORDER BY timer_value
                LIMIT 5
            ''')
            lowest_individual_clicks = cursor.fetchall()

            cursor.execute('''
                SELECT user_name, MIN(timer_value) AS lowest_click_time
                FROM button_clicks
                GROUP BY user_id
                ORDER BY lowest_click_time
                LIMIT 5
            ''')
            lowest_user_clicks = cursor.fetchall()

            cursor.execute('''
                SELECT
                    user_name,
                    SUM(43200 - timer_value) AS total_time_claimed
                FROM button_clicks
                GROUP BY user_id
                ORDER BY total_time_claimed DESC
                LIMIT %s
            ''', (num_entries,))
            most_time_claimed = cursor.fetchall()
            
            # Title with hella emojis but in the dnd style flavor text
            embed = nextcord.Embed(title='🏆 The Leaderboard Legends of the Button 🏆')

            top_clicks_value = '\n'.join(
                f'{user.replace(".", "")}: {clicks} clicks ({" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)})'
                for user, clicks, seq in most_clicks
            )
            embed.add_field(name='Mightiest Clickers (Most Clicks)', value=top_clicks_value, inline=False)

            lowest_individual_clicks_value = '\n'.join(
                f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                for user, click_time in lowest_individual_clicks
            )
            embed.add_field(name='Swiftest Clicks (Lowest Time When Clicked)', value=lowest_individual_clicks_value, inline=False)

            lowest_user_clicks_value = '\n'.join(
                f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                for user, click_time in lowest_user_clicks
            )
            embed.add_field(name='Nimblest Warriors (Lowest Time Clickers)', value=lowest_user_clicks_value, inline=False)

            most_time_claimed_value = '\n'.join(
                f'{user.replace(".", "")}: {format_time(time_claimed)}'
                for user, time_claimed in most_time_claimed
            )
            embed.add_field(name='⌛ Temporal Titans (Most Time Claimed) ⌛', value=most_time_claimed_value, inline=False)

            color = get_color_state(lowest_individual_clicks[0][1])
            embed.color = nextcord.Color.from_rgb(*color)

            embed.description = "Gather round, brave adventurers, and marvel at the legends whose names shall be etched in the button's eternal memory!"

            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving leaderboard: {e}, {tb}')
            logger.error(f'Error retrieving leaderboard: {e}, {tb}')
            await message.channel.send('An error occurred while retrieving the leaderboard. The button archives are in disarray!')
    
    elif message.content.lower() == 'help':
        # How to use myrank and leaderboard
        embed = nextcord.Embed(title='Help', description='How to use `myrank` and `leaderboard`')
        embed.add_field(name='myrank', value='Check your personal stats', inline=False)
        embed.add_field(name='leaderboard', value='Check the top 10 clickers', inline=False)
        embed.add_field(name='check', value='Check if you have a click ready', inline=False)
        embed.add_field(name='lore', value='Read the lore of The Button', inline=False)
        embed.add_field(name='drunklore', value='Read the drunken lore of The Button', inline=False)
        embed.add_field(name='blackoutdrunklore', value='Read the blackout drunken lore of The Button', inline=False)
        embed.set_footer(text='May your clicks be swift and true, adventurer!')
        # purple color
        color = (106, 76, 147)
        embed.color = nextcord.Color.from_rgb(*color)
        await message.channel.send(embed=embed)
    
    elif message.content.lower() == 'check':
        # Check if the user has a click ready   
        is_other_user = False
        if len(message.content.split(" ")) > 1:
            user_check_id = int(message.content.split(" ")[1][3:-1])
            is_other_user = True
        else:
            user_check_id = message.author.id
        
        try:
            cursor.execute('''
                SELECT COUNT(*) AS click_count
                FROM button_clicks
                WHERE user_id = %s AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 HOUR)
            ''', (user_check_id,))
            result = cursor.fetchone()
            click_count = result[0]

            if not is_other_user:
                if click_count == 0:
                    response = "Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. Go forth and claim your glory!"
                    #add check emoji at beginning of response
                    response = "✅ " + response
                else:
                    response = "Alas, noble warrior, you must rest and gather your strength. The button shall beckon you again when the time is right."
                    # add x
                    response = "❌ " + response
            else: #Referencing another user in dnd style flavor text
                if click_count == 0:
                    response = "Ah, a brave adventurer's spirit is ready, and the button awaits their valiant click. Go forth and claim your glory!"
                else:
                    response = "Alas, noble warrior, they must rest and gather their strength. The button shall beckon them again when the time is right."
                    # add x
                    response = "❌ " + response

            embed = nextcord.Embed(description=response)
            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error checking user cooldown: {e}, {tb}')
            logger.error(f'Error checking user cooldown: {e}, {tb}')
            await message.channel.send('An error occurred while checking your cooldown status.')
    
    elif message.content.lower() == 'lore':
        try:
            lore_text = """
                🕰️ In a realm where **time itself hangs in the balance**, a peculiar artifact known as "**The Button**" has emerged. *Forged by the hands of an ancient sorcerer*, this mystical device holds the power to manipulate the very fabric of reality. 🌌

                __Legend has it that as long as The Button remains untouched, the world remains stable.__ However, if left idle for too long, the consequences could be *catastrophic*. ⚠️ It is said that when the timer reaches zero, ***an apocalyptic event will be unleashed upon the land.*** 💥

                To prevent this calamity, **brave adventurers** from far and wide have gathered in the legendary tavern owned by the skilled VRChat avatar craftsman, **Drunk Harpy**. 🍻 In this virtual haven, adventurers take turns to press The Button and reset the timer. *Each click buys precious time*, but the adventurers must exercise caution, for they can only press The Button **once every few hours**. ⏳

                As the adventurers continue their valiant efforts, they **earn titles and accolades** based on the color of The Button at the time of their click. 🎨 The colors range from the *ominous red*, signifying imminent danger, to the *calming purple*, indicating a moment of respite. 😌

                __The most dedicated and skilled adventurers rise through the ranks__, their names etched in the annals of history as the "**Mightiest Clickers**" and the "**Nimblest Warriors**." 🏆 They become the stuff of legends, *inspiring others to join the cause* and keep The Button alive. 💪

                But the true nature of The Button remains **shrouded in mystery**. Some whisper that it is a test of the adventurers' resolve, *a cosmic game orchestrated by higher powers.* 🔮 Others believe that The Button holds the key to unlocking ***untold secrets and treasures***, perhaps even granting the power to bring **Drunk Harpy's avatar creations to life**. 🎭

                __Regardless of its true purpose, one thing is certain__: the fate of the realm rests upon the shoulders of these brave adventurers, united in their quest to keep The Button alive and prevent the impending doom. 🛡️ *Their clicks echo through the ages*, a testament to their **unwavering determination** and the power of unity in the face of an uncertain future. 🌈

                ***Will you join the ranks of these valiant heroes in Drunk Harpy's virtual tavern and lend your click to the cause?*** ⚔️ **The Button awaits, and the fate of the world hangs in the balance...** 🌍
            """

            embed = nextcord.Embed(title="📜 __The Lore of The Button__ 📜", description=lore_text)
            embed.set_footer(text="⚡ *May your clicks be swift and true, adventurer!* ⚡")

            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving lore: {e}, {tb}')
            logger.error(f'Error retrieving lore: {e}, {tb}')
            await message.channel.send('❌ **An error occurred while retrieving the lore.** *The ancient archives seem to be temporarily sealed!* ❌')
    
    elif message.content.lower() == 'drunklore':
        try:
            lore_text = """
                🧙‍♂️ *Gether round, young ones, and let old Wizzerd Herpy spin you a tail of MAGIC and... and... 🌟 WONDER! Yeah, that's it!* 🍆

                In a land far, far away 🌎... or was it near? 🤔 I don't rememberrr... ANYWAY! There's this *MYSTICAL BUTTON* of *IMMENSE POWER!* ⚡🔮 Legend says... or was it a prophecy? 🤷‍♂️ Well, somethin' about this button holdin' the very *FABRIC OF REALITY* together! 🧵🥒

                But *BEWARE*, my young... uhh... 🍳 apprentices! If the button is left *UNATTENDED* for too long, the world shall *UNRAVEL* like a cheap sweater! 🧶💔 Or was it a scarf? I forget. 😴

                *FEAR NOT*, however! There are *BRAVE HEROES* 🦸‍♀️🦸‍♂️ who have taken up the *SACRED DUTY* of pressing the button! They gather in a *MAGICAL TAVERN* 🍻, owned by the *ILLUSTRIOUS AVATAR CRAFTER*, Drunk Harpy! 🎨 She makes the BEST cocktails! 🍹😋

                Now, where was I? Oh right, the heroes! 💂‍♀️💂‍♂️ They take turns 🔄 pressing the button, each click buying precious... precious... ⌛ TIME! That's the word! The button demands to be pressed every few hours! ⏰ Or was it minutes? 🤔

                And the COLORS! 🌈 Oh, the beautiful colors of the button! 🎨 From the *OMINOUS RED* 🟥 to the *TRANQUIL PURPLE* 🟪... I think I'm forgetting some colors, but who cares? 😅 Each color means... something! 💜

                The most *DEDICATED* and *SKILLFUL* heroes shall be forever remembered! 💪 Their names shall be *ETCHED*... or was it *SKETCHED*? 🤔 In the *ANNALS OF HISTORY!* 📜 Heh, I said "annals." 🍑😂

                But I DIGRESS! 🙄 The fate of the... the... 🌍 WORLD! Yes, that's right! It rests upon the shoulders of these *VALIANT HEROES!* 🎖️ Their clicks 🖱️ are a testament to their *UNWAVERING RESOLVE* and... and... something about *UNITY!* 🤝

                So, WHAT ARE YOU WAITING FOR? 🕰️ Join the ranks, young ones! 🎖️ Lend your click to the *GREAT CAUSE!* The button *BECKONS!* 🗺️🎉 Adventure awaits! Or was it danger? 🤔 Ah, who cares? Just click the damn thing! 😂🍻
            """

            embed = nextcord.Embed(title="🔮 __Wizzerd Herpy's *ENCHANTING* Button... Thing__ 🧙‍♂️", description=lore_text)
            embed.set_footer(text="🧪 *MAY YOUR CLICKS BE INFUSED WITH... WITH... MAGIC! Yeah, that's it!* ⚗️🧦")

            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving drunk wizard lore: {e}, {tb}')
            logger.error(f'Error retrieving drunk wizard lore: {e}, {tb}')
            await message.channel.send('🍄 **Oh dear, Wizzerd Herpy had too much of the... the... *ENCHANTED ELIXIR!*** 🍾💊 *The drunk wizard lore is temporarily lost in the astral plane!* 🌀🧻')
    
    elif message.content.lower() == 'blackoutdrunklore':
        try:
            lore_text = """
                🧙‍♂️ *Gether 🦄 round, yung ones, and let old 🌮 Wizzerd Herpy 🍕 spin you a tail �lobster of 🎉 TRAGIC and... and... 🌟 BLUNDER! Yeah, 🛴 that's it!* 🍆

                In a 🎡 land 🌮🌮 far, far a🐋... or was it 🦜 near? 🤔 I don't reme🍔... ANY🍉! There's this *MYTHICAL MUTTON* 🥩 of *IMMENSE FLOUR!* ⚡🔮 Legend says... or was it a 🥐 prophecy? 🤷‍♂️ Well, 🚽 somethin' about this 🎿 button holdin' the very *FABRIC OF 🧻...*

                ˙˙˙ɹǝpuoʍ puɐ ɔıƃɐɯ ɟo ǝlɐʇ ɐ noʎ uıds ʎdɹǝɥ pɹǝzzıʍ plo ʇǝl puɐ 'sǝuo ƃunoʎ 'punoɹ ɹǝɥʇǝƃ 👁️👄👁️

                But *BE🍇*, my 🎡 yung... uhh... 🍳 applesauce! If the button is left *UNATTENDED* for too long, the 🌍 shall *UNRAVEL* 🪱 like a cheap 🧦! Or was it a 🧣? I forklift. 😴

                *FEAR 🌽*, however! There are *BRAVE 🍔* 🦸‍♀️🦸‍♂️ who have taken up the *SACRED 🚽* of pressing the 🛎️! They gather in a *MAGICAL 🍺*, owned by the *ILLUSTRIOUS 🎢 CRATER*, Drunk 🐟! 🎨 She makes the BEST 🍹😋

                asnfjafhlhgsdg 🍗 adshfhafja 🌭 ieuruijfsd 🥗 jfaiefawefn 🥜

                Now, where was 👁️? Oh right, the 🦸‍♀️💂‍♂️! 💂‍♀️💂‍♂️ They take 🔄 pressing the button, each click buying prescriptions... precious... ⌛ THYME! That's the world! The button demands to be pressed every few 🕰️! Or was it 🐜? 🤔

                And the COLLARS! 🌈 Oh, the bootiful 🎨 of the button! 🎨 From the *OMINOUS 🟥* to the *TRANQUIL 🟪*... I think I'm forgiving some colors, but who cars? 😅 Each color memes... something! 💜

                The most *DETICATED* and *SKILLESS* heroes shall be forever rememembered! 💪 Their names shall be *ETCHED*... or was it *SKETCHED*? 🤔 In the *ANIMALS OF HISTORY!* 📜 Heh, I said "animals." 🍑😂

                But I 🤾‍♂️! 🙄 The fate of the... the... 🌍 WORD! Yes, that's fight! It rusts upon the boulders of these *VIOLENT HEROES!* 🎖️ Their clocks 🖱️ are a tastemint to their *UNWAVERING REVOLVE* and... and... something about *UNITY!* 🤝

                So, WHAT ARE YOU WAITING FOR? 🕰️ Join the ranks, yung ones! 🎖️ Lend your click to the *GRATE CAUSE!* The button *BACONS!* 🗺️🎉 Adventurer awaits! Or was it park ranger? 🤔 Ah, who cares? Just lick the damn thing! 😂🍻

                zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
            """

            embed = nextcord.Embed(title="🔮 __Wizzerd Herpy's *ENCHANTING* Butt... Thing__ 🧙‍♂️", description=lore_text)
            embed.set_footer(text="🧪 *MAY YOUR CLOCKS BE INFUSED WITH... WITH... TRAGIC! Yeah, that's it!* ⚗️🧦")

            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving blackout drunk wizard lore: {e}, {tb}')
            logger.error(f'Error retrieving blackout drunk wizard lore: {e}, {tb}')
            await message.channel.send('🍄 **Oh dear, Wizzerd Herpy had too much of the... the... *ENCHANTED ELIXIR!*** 🍾💊 *The blackout drunk wizard lore is temporarily lost in the astral plane!* 🌀🧻 hfjksdhfdshf 🍔 jfhdsajfhkjads 🍕')
    
    lock.release()

@bot.event
async def on_error(event, *args, **kwargs):
    if event == "on_message":
        print(f"Unhandled message: {args[0]}")
        logger.error(f"Unhandled message: {args[0]}")

    if isinstance(args[0], nextcord.HTTPException):
        if args[0].status == 429:  # Rate limit status code
            retry_after = args[0].response.headers["Retry-After"]
            print(f"Rate limited. Retrying in {retry_after} seconds.")
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            await asyncio.sleep(float(retry_after))
            return
        
    raise

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    logger.info(f'Bot connected as {bot.user}')
    for guild in bot.guilds:
        print(f'Connected to guild: {guild.name}')
        logger.info(f'Connected to guild: {guild.name}')
        # Send "sb" to the game channel to start the game
        game_channel = bot.get_channel(config['button_channel_id'])
        await game_channel.send('sb')
        

@bot.event
async def on_disconnect():
    print(f'Bot disconnected')
    logger.info(f'Bot disconnected')
    #reconnect bot
    await bot.connect(reconnect=True)
    
    
bot.run(config['discord_token'])