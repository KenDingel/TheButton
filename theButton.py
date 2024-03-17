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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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

def reconnect_cursor():
    global db, cursor
    if not db.is_connected():
        global cursor
        db = get_db_connection()
        cursor = db.cursor()

# Set up the bot with the necessary intents
intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

lock = asyncio.Lock()

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
            "As a reward for your bravery, you'll earn a exclusive role based on the color you click!\n"
            "Use `myrank` to check your personal stats and `leaderboard` to see how you stack up against other fearless clickers! \n\n"
            "Do you have what it takes to keep the button alive and prevent the timer from reaching zero?\n\n"
            "*Based on the Reddit April Fools event in 2015. https://en.wikipedia.org/wiki/The_Button_(Reddit)*"
        )
        await bot.get_channel(config['button_channel_id']).send(explanation)

        # Create the button message
        embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='Click the button to start the game!')
        message = await bot.get_channel(config['button_channel_id']).send(embed=embed, view=ButtonView(config['timer_duration']))
        config['button_message_id'] = message.id

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
        
        if not update_timer.is_running():
            update_timer.start()
    except Exception as e:
        tb = traceback.format_exc()
        print(f'Error creating button message: {e}, {tb}')
        logger.error(f'Error creating button message: {e}, {tb}')

@tasks.loop(seconds=5)
async def update_timer():
    try:
        try:
            button_channel = bot.get_channel(config['button_channel_id'])
            button_message = await button_channel.fetch_message(config['button_message_id'])
        except nextcord.NotFound:
            print('Button message not found, creating a new button message...')
            logger.error('Button message not found, creating a new button message...')
            await create_button_message()
            return
        
        # Reconnect to the database if the connection is lost
        global cursor, db
        if not db.is_connected():
            db = get_db_connection()
            cursor = db.cursor()

        embed = button_message.embeds[0]

        # Retrieve the latest button click timestamp from the database
        cursor.execute('SELECT user_name, click_time, timer_value FROM button_clicks ORDER BY id DESC LIMIT %s', (1,))
        result = cursor.fetchone()

        if result:
            user_name, latest_click_time, last_timer_value = result
            latest_click_time = latest_click_time.replace(tzinfo=timezone.utc) if latest_click_time.tzinfo is None else latest_click_time
            elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds()
            timer_value = max(config['timer_duration'] - elapsed_time, 0)

            # Get color state and format latest click time for display
            color_state = get_color_state(last_timer_value)
            color_index = COLOR_STATES.index(color_state)
            color_name = ["Red", "Orange", "Yellow", "Green", "Blue", "Purple"][color_index]
            emoji = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣"][color_index]
            
            formatted_time = f'<t:{int(latest_click_time.timestamp())}:R>'
            latest_user_info = f'{user_name} {formatted_time} achieving {emoji} {color_name} role.'
        else:
            timer_value = config['timer_duration']
            latest_user_info = "No presses yet."

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
            for color_name in ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple']:
                role = nextcord.utils.get(Guild.roles, name=color_name)
                count = len(role.members)
                color_distribution.append(f"- {color_name}: {count}")
            embed.add_field(name='Color Role Distribution', value='\n'.join(color_distribution), inline=False)
        else:
            timer_value = int(timer_value)
            embed.clear_fields()
            latest_press_emoji = "👤"
            embed.add_field(name=f'{latest_press_emoji} Latest Click', value=latest_user_info, inline=False)
        
            # Calculate and display how long the game has been running
            cursor.execute('SELECT MIN(click_time) FROM button_clicks')
            start_time = cursor.fetchone()[0]
            if start_time:
                total_clicks = 0
                cursor.execute('SELECT COUNT(*) FROM button_clicks')
                result = cursor.fetchone()
                total_clicks = result[0] if result else 0
                start_time = start_time.replace(tzinfo=timezone.utc)
                elapsed_time = (datetime.datetime.now(timezone.utc) - start_time).total_seconds()
                elapsed_time_clicks_str = f"{format(int(elapsed_time//3600), '02d')} hours {format(int(elapsed_time%3600//60), '02d')} minutes and {format(int(elapsed_time%60), '02d')} seconds, with {total_clicks} total clicks"
                embed.add_field(name='📊 Lifetime Game Stats', value=elapsed_time_clicks_str, inline=False)
            
            # Generate the timer image and set it as the embed image
            timer_image_path = generate_timer_image(timer_value)
            embed.set_image(url=f'attachment://{os.path.basename(timer_image_path)}')

            pastel_color = get_color_state(timer_value)
            embed.color = nextcord.Color.from_rgb(*pastel_color)

            # Update the button view for users on cooldown
            cooldown_manager.remove_expired_cooldowns()
            cursor.execute('SELECT user_id FROM users WHERE cooldown_expiration > %s', (datetime.datetime.now(timezone.utc),))
            cooldown_user_ids = [user_id for user_id, in cursor]
            for user_id in cooldown_user_ids:
                button_view = ButtonView(timer_value, user_id)
                button_view.children[0].disabled = True
                
            await button_message.edit(embed=embed, file=nextcord.File(timer_image_path), view=button_view)
            
            # Generate the timer image and set it as the embed image
            timer_image_path = generate_timer_image(timer_value)
            embed.set_image(url=f'attachment://{os.path.basename(timer_image_path)}')

            pastel_color = get_color_state(timer_value)
            embed.color = nextcord.Color.from_rgb(*pastel_color)

            button_view = ButtonView(timer_value, user_id)

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
    def __init__(self, timer_value, user_id: int = None):
        super().__init__(timeout=None)  # Set timeout=None if you want the buttons to be always active
        self.timer_value = timer_value
        self.user_id = user_id
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
        await interaction.response.defer(ephemeral=True)
        try:
            await lock.acquire()
            print(f'Button clicked by {interaction.user}!')
            logger.info(f'Button clicked by {interaction.user}!')
            button_channel = bot.get_channel(config['button_channel_id'])
            button_message = await button_channel.fetch_message(config['button_message_id'])

            embed = button_message.embeds[0]

            # if cursor is not connected
            global cursor, db
            if not db.is_connected():
                db = get_db_connection()
                cursor = db.cursor()
            
            cursor.execute('SELECT click_time FROM latest_click ORDER BY id DESC LIMIT 1')
            result = cursor.fetchone()

            if result:
                latest_click_time = result[0]
                latest_click_time = latest_click_time.replace(tzinfo=timezone.utc)
                elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time).total_seconds()
                current_timer_value = max(config['timer_duration'] - elapsed_time, 0)
            else:
                current_timer_value = config['timer_duration']

            if current_timer_value <= 0:
                await interaction.followup.send("The game has already ended!", ephemeral=True)
                lock.release() 
                return

            cursor.execute('SELECT COUNT(*) FROM button_clicks WHERE user_id = %s AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 HOUR)', (interaction.user.id,))
            result = cursor.fetchone()
            click_count = result[0] if result else 0

            if click_count >= 1:
                cursor.execute('SELECT click_time FROM button_clicks WHERE user_id = %s ORDER BY id DESC LIMIT 1', (interaction.user.id,))
                result = cursor.fetchone()
                if result:
                    last_click_time = result[0]
                    last_click_time = last_click_time.replace(tzinfo=timezone.utc)
                    cooldown_remaining = (last_click_time + datetime.timedelta(hours=3)) - datetime.datetime.now(timezone.utc)
                    cooldown_remaining = int(cooldown_remaining.total_seconds())
                    # Format in H M S labeled format
                    formatted_cooldown  = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                    await interaction.followup.send(f'You have already clicked the button in the last 3 hours. Please try again in {formatted_cooldown}', ephemeral=True)
                else:
                    await interaction.followup.send('An error occurred while checking your cooldown time.', ephemeral=True)
                lock.release()
                return

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
            await interaction.followup.send("Button clicked! You have earned the role of " + role_name + "!", ephemeral=True)
            
            cooldown_duration = datetime.timedelta(hours=3)
            color_rank = role_name
            cooldown_manager.add_or_update_user(interaction.user.id, cooldown_duration, color_rank, current_timer_value)
            
            color_emoji = get_color_emoji(current_timer_value)
            # remaining_time = format_time(current_timer_value)
            # Formatted in H M S labeled format
            formatted_remaining_time = f"{format(int(current_timer_value//3600), '02d')} hours {format(int(current_timer_value%3600//60), '02d')} minutes and {format(int(current_timer_value%60), '02d')} seconds"
            embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {role_name} rank!", color=nextcord.Color.from_rgb(*color_state))
            chat_channel = bot.get_channel(config['chat_channel_id'])
            await chat_channel.send(embed=embed)
            
            # Set the cooldown for the user
            cooldown_manager.add_or_update_user(interaction.user.id, datetime.timedelta(hours=3), role_name, current_timer_value)
            lock.release()
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error processing button click: {e}, {tb}')
            logger.error(f'Error processing button click: {e}, {tb}')
            await interaction.followup.send("An error occurred while processing the button click.", ephemeral=True)
            lock.release()
            
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.channel.id != config['button_channel_id'] and message.channel.id != config['chat_channel_id']:
        return

    await lock.acquire()
    
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

    elif message.content.lower() == 'myrank':
        try:
            cursor.execute('''
                SELECT
                    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY MIN(timer_value) ASC) AS 'rank',
                    user_name,
                    COUNT(*) AS total_clicks,
                    MIN(timer_value) AS lowest_click
                FROM button_clicks
                GROUP BY user_id
                ORDER BY MIN(timer_value) ASC;
            ''')
            results = cursor.fetchall()

            user_rank = None
            user_total_clicks = None
            user_lowest_click = None

            for rank, user_name, total_clicks, lowest_click in results:
                if str(message.author) == user_name:
                    user_rank = rank
                    user_total_clicks = total_clicks
                    user_lowest_click = lowest_click
                    break

            if user_rank is not None:
                color = get_color_state(user_lowest_click)
                embed = nextcord.Embed(
                    title='Your Stats',
                    description=f'Rank: {user_rank}\nTotal Clicks: {user_total_clicks}\nLowest Click Time: {format_time(user_lowest_click)}',
                    color=nextcord.Color.from_rgb(*color)
                )
                await message.channel.send(embed=embed)
            else:
                await message.channel.send('You have not clicked the button yet.')

        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving user rank: {e}, {tb}')
            logger.error(f'Error retrieving user rank: {e}, {tb}')
            await message.channel.send('An error occurred while retrieving your rank.')

    elif message.content.lower() in ['leaderboard', 'scores', 'scoreboard', 'top']:
        try:
            cursor.execute('SELECT user_name, COUNT(*) AS total_clicks FROM button_clicks GROUP BY user_id ORDER BY total_clicks DESC LIMIT 10')
            most_clicks = cursor.fetchall()

            cursor.execute('SELECT user_name, MIN(timer_value) AS lowest_click FROM button_clicks GROUP BY user_id ORDER BY lowest_click ASC LIMIT 10')
            lowest_clicks = cursor.fetchall()

            embed = nextcord.Embed(title='The Button Leaderboard')
            embed.add_field(name='Most Clicks', value='\n'.join(f'{user.replace(".", "")}: {clicks}' for i, (user, clicks) in enumerate(most_clicks)), inline=False)
            embed.add_field(name='Lowest Click Time', value='\n'.join(f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}' for i, (user, click_time) in enumerate(lowest_clicks)), inline=False)
            color = get_color_state(lowest_clicks[0][1])
            embed.color = nextcord.Color.from_rgb(*color)
            await message.channel.send(embed=embed)
        except Exception as e:
            tb = traceback.format_exc()
            print(f'Error retrieving leaderboard: {e}, {tb}')
            logger.error(f'Error retrieving leaderboard: {e}, {tb}')
            await message.channel.send('An error occurred while retrieving the leaderboard.')
            
    elif message.content.lower() == 'help':
        # How to use myrank and leaderboard
        embed = nextcord.Embed(title='Help', description='How to use `myrank` and `leaderboard`')
        embed.add_field(name='myrank', value='Check your personal stats', inline=False)
        embed.add_field(name='leaderboard', value='Check the top 10 clickers', inline=False)
        # purple color
        color = (106, 76, 147)
        embed.color = nextcord.Color.from_rgb(*color)
        await message.channel.send(embed=embed)
    lock.release()

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')
    logger.info(f'Bot connected as {bot.user}')

@bot.event
async def on_disconnect():
    print(f'Bot disconnected')
    logger.info(f'Bot disconnected')
    db_pool.close()

bot.run(config['discord_token'])