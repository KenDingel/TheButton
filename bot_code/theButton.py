# The button.py
import os
import asyncio
import datetime
from datetime import timezone
import traceback
import signal

import nextcord
from nextcord import Guild
from nextcord.ext import commands, tasks

from utils import *
from database import *
from end_game import get_end_game_embed
from full_text import *
from game_cache import *


intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def setup_roles(guild_id):
    guild = bot.get_guild(guild_id)
    for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
        role = nextcord.utils.get(guild.roles, name=color_name)
        if role is None:
            role = await guild.create_role(name=color_name, color=nextcord.Color.from_rgb(*color_value))
        else:
            await role.edit(color=nextcord.Color.from_rgb(*color_value))
    logger.info(f"In {guild.name}, roles have been set up.")

async def create_button_message(game_id):
    logger.info(f'Creating button message for game {game_id}...')
    try:
        game_session_config = get_game_session_by_id(game_id)
        embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='**Keep the button alive!**')
        button_channel = bot.get_channel(game_session_config['button_channel_id'])
        # Delete last 5 messages in the button channel from the bot with embeds
        async for message in button_channel.history(limit=5):
            if message.author == bot.user and message.embeds:
                await message.delete()
                
        # see if explaination text message contents already exists in channel, if not send it
        if not EXPLAINATION_TEXT in [msg.content async for msg in button_channel.history(limit=5)]:
            await bot.get_channel(game_session_config['button_channel_id']).send(EXPLAINATION_TEXT)
        message = await button_channel.send(embed=embed, view=ButtonView(game_session_config['timer_duration']))
        return message
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error creating button message: {e}, {tb}')
        return None

async def get_button_message(game_id):
    task_run_time = datetime.datetime.now(timezone.utc)
    game_id = int(game_id)
    
    if game_id in button_message_cache.messages:
        try:
            message = button_message_cache.get_game_id(game_id)
            logger.info(f'Getting button message from cache for game {game_id}...')
            return message
        except Exception as e:
            tb = traceback.format_exc()
    
    game_session_config = game_sessions_dict()[game_id]
    #logger.info(f'Getting button message for game {game_id}...\nSession: {game_session_config}')
    if not game_session_config:
        logger.error(f'No game session found for game {game_id}')
        update_local_game_sessions()
        game_session_config = game_sessions_dict()[game_id]
    button_channel = bot.get_channel(int(game_session_config['button_channel_id']))
    # Check for existing button based on it being the latest message and is embed
    async for message in button_channel.history(limit=5):
        if message.author == bot.user and message.embeds:
            # If no existing button message found, create a new one
            logger.error(f'No existing button message found for game {game_id}, creating a new one...')
            message = await create_button_message(game_id)
            button_message_cache.update_message_cache(message, game_id)
            task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
            logger.info(f'Get button message run time: {task_run_time.total_seconds()} seconds')
            return message
    return None

paused_games = []

@tasks.loop(seconds=1.5)
async def update_timer():
    global lock, paused_games, game_cache
    for game_id, game_session in game_sessions_dict().items():
        if paused_games and game_id in paused_games:
            logging.info(f'Game {game_id} is paused, skipping...')
            continue
        game_id = str(game_id)
        logger.info(f'Updating timer for game {game_id}...')
        await lock.acquire()
        task_start_run_time = datetime.datetime.now(timezone.utc)
        try:
            cache_data = game_cache.get_game_cache(game_id)
            last_update_time = None
            if cache_data:
                latest_click_time_overall = cache_data['latest_click_time']
                total_clicks = cache_data['total_clicks']
                last_update_time = cache_data['last_update_time']
                total_players = cache_data['total_players']
                user_name = cache_data['latest_player_name']
            else:
                query = f'''
                    SELECT users.user_name, button_clicks.click_time, 
                        (SELECT COUNT(*) FROM button_clicks WHERE game_id = {game_id}) AS total_clicks,
                        (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = {game_id}) AS total_players
                    FROM button_clicks
                    INNER JOIN users ON button_clicks.user_id = users.user_id
                    WHERE button_clicks.game_id = {game_id}
                    ORDER BY button_clicks.id DESC
                    LIMIT 1
                '''
                params = ()
                result = execute_query(query, params, is_timer=True)
                if not result: 
                    logger.error(f'No results found for game {game_id} cache')
                    if paused_games:
                        paused_games = paused_games.append(game_id)
                    else:
                        paused_games = [game_id]
                    return
                result = result[0]
                user_name, latest_click_time_overall, total_clicks, total_players = result
                latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc) if latest_click_time_overall.tzinfo is None else latest_click_time_overall
                game_cache.update_game_cache(game_id, latest_click_time_overall, total_clicks, total_players, user_name)
                last_update_time = datetime.datetime.now(timezone.utc)
            elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time_overall).total_seconds()
            timer_value = max(game_session['timer_duration'] - elapsed_time, 0)

            if last_update_time is None or not last_update_time:
                last_update_time = datetime.datetime.now(timezone.utc)
            # if datetime.datetime.now(timezone.utc) - last_update_time > datetime.timedelta(minutes=15):
            #     logger.info(f'Updating cache for game {game_id}, since last update was more than 15 minutes ago...')
            #     query = f'''
            #         SELECT users.user_name, button_clicks.click_time, 
            #             (SELECT COUNT(*) FROM button_clicks WHERE game_id = {game_id}) AS total_clicks,
            #             (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = {game_id}) AS total_players
            #         FROM button_clicks
            #         INNER JOIN users ON button_clicks.user_id = users.user_id
            #         WHERE button_clicks.game_id = {game_id}
            #         ORDER BY button_clicks.id DESC
            #         LIMIT 1
            #     '''
            #     params = ()
            #     result = execute_query(query, params, is_timer=True)
            #     if result:
            #         result = result[0]
            #         if result:
            #             user_name, latest_click_time_overall, total_clicks, total_players = result
            #             latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc) if latest_click_time_overall.tzinfo is None else latest_click_time_overall
            #             game_cache.update_game_cache(game_id, latest_click_time_overall, total_clicks, total_players, user_name)
            #     else:
            #         logger.error(f'No results found for game {game_id}')
            #         return
            color_state = get_color_state(timer_value)
            color_index = COLOR_STATES.index(color_state)
            color_name = ["Red", "Orange", "Yellow", "Green", "Blue", "Purple"][color_index]
            emoji = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣"][color_index]
            formatted_time = f'<t:{int(latest_click_time_overall.timestamp())}:R>'
            time_value_formatted = latest_click_time_overall.strftime('%Y-%m-%d %H:%M:%S %Z')
            latest_user_info = f'{formatted_time} {user_name} clicked {emoji} {color_name} at {time_value_formatted}!'
            button_message = await get_button_message(game_id)
            embed = button_message.embeds[0]
            if timer_value <= 0:
                embed = get_end_game_embed(game_id)
                await button_message.edit(embed=embed)
                update_timer.stop()
                logger.info(f'Game {game_id} Ended!')
            else:
                #task03_run_time = datetime.datetime.now(timezone.utc)
                embed.clear_fields()
                embed.add_field(name='👤 Latest Click', value=latest_user_info, inline=False)
                note = "Due to the magic bugs, the lifetime of the button has been reset.\n**ALL clicks already made will be counted in the final score.**"
                embed.add_field(name='📜 Note', value=note, inline=False)

                start_time = game_session['start_time'].replace(tzinfo=timezone.utc)
                elapsed_time = datetime.datetime.now(timezone.utc) - start_time

                elapsed_days = elapsed_time.days
                elapsed_hours = elapsed_time.seconds // 3600
                elapsed_minutes = (elapsed_time.seconds % 3600) // 60
                elapsed_seconds = elapsed_time.seconds % 60
                elapsed_seconds = round(elapsed_seconds, 2)
                elapsed_time_str = f'{elapsed_days} days, {elapsed_hours} hours, {elapsed_minutes} minutes, {elapsed_seconds} seconds'
                total_clicks_msg = f'{total_clicks} clicks'
                total_players_msg = f'{total_players}'

                embed.description = f'The game ends when the timer hits 0.\nClick the button to reset it and keep the game going!\n\nValiant clickers, you have kept the button alive for...\n**{elapsed_time_str}**!\nIn your pursuit of glory, {total_clicks_msg} have been made by {total_players_msg} adventurers! 🛡️🗡️🏰\n\nWill you join the ranks of the brave and keep the button alive?'
                embed.set_footer(text=f'The Button Game by Regen2Moon; Inspired by Josh Wardle')
                file_buffer = generate_timer_image(timer_value)
                embed.set_image(url=f'attachment://{file_buffer.filename}')
                pastel_color = get_color_state(timer_value)
                embed.color = nextcord.Color.from_rgb(*pastel_color)
                logger.info(f'11 Current time run time: {(datetime.datetime.now(timezone.utc) - task_start_run_time).total_seconds()} seconds')
                button_view = ButtonView(timer_value)
                await button_message.edit(embed=embed, file=file_buffer, view=button_view)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error updating timer: {e}, {tb}')
        finally:
            lock.release()

class UserManager:
    def __init__(self):
        self.status = None

    def add_or_update_user(self, user_id, cooldown_expiration, color_rank, timer_value, user_name, game_id, latest_click_var=None):
        global cursor, db
        try:
            #cooldown_expiration = datetime.datetime.now(timezone.utc) + cooldown_duration
            query = '''
                INSERT INTO users (user_id, cooldown_expiration, color_rank, total_clicks, lowest_click_time, latest_click_time, user_name, game_id)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    cooldown_expiration = VALUES(cooldown_expiration),
                    color_rank = VALUES(color_rank),
                    total_clicks = total_clicks + 1,
                    lowest_click_time = LEAST(lowest_click_time, VALUES(lowest_click_time)),
                    latest_click_time = VALUES(latest_click_time)
            '''
            latest_click_time = latest_click_var if latest_click_var else datetime.datetime.now(timezone.utc)
            params = (user_id, cooldown_expiration, color_rank, timer_value, latest_click_time, user_name, game_id)
            success = execute_query(query, params, commit=True)
            if not success:
                return False
            return True
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error adding or updating user: {e}, {tb}')
            return False

    def remove_expired_cooldowns(self):
        global cursor, db
        try:
            query = 'UPDATE users SET cooldown_expiration = NULL WHERE cooldown_expiration <= %s'
            params = (datetime.datetime.now(timezone.utc),)
            success = execute_query(query, params)
            if not success: 
                return
            db.commit()
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error removing expired cooldowns: {e}, {tb}')

user_manager = UserManager()

class ButtonView(nextcord.ui.View):
    def __init__(self, timer_value):
        super().__init__(timeout=None)
        self.timer_value = timer_value
        self.add_button()

    def add_button(self):
        button_label = "Click me!"
        color = get_color_state(self.timer_value)
        style = get_button_style(color)
        self.clear_items()
        button = TimerButton(style=style, label=button_label, timer_value=self.timer_value)
        self.add_item(button)

class TimerButton(nextcord.ui.Button):
    def __init__(self, style, label, timer_value):
        super().__init__(style=style, label=label)
        self.timer_value = timer_value

    async def callback(self, interaction: nextcord.Interaction):
        global paused_games, game_cache
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as e:
            logger.error(f'Error deferring response: {e}')
            #lock.release()
            return
            
        await lock.acquire()
        task_run_time = datetime.datetime.now(timezone.utc)
        try:
            click_time = datetime.datetime.now(timezone.utc)
            
            try:
                game_session = get_game_session_by_guild_id(interaction.guild.id)
                game_id = game_session['game_id']
                button_message = await get_button_message(game_id)
                embed = button_message.embeds[0]

                query = f'''
                    SELECT
                        (SELECT MAX(click_time) FROM button_clicks WHERE game_id = {game_id}) AS latest_click_time_overall,
                        MAX(IF(user_id = %s AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 6 HOUR), click_time, NULL)) AS latest_click_time_user,
                        (SELECT COUNT(*) FROM button_clicks WHERE game_id = {game_id}) AS total_clicks,
                        (SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = {game_id}) AS total_players
                    FROM button_clicks
                    WHERE game_id = {game_id}
                '''
                params = (interaction.user.id,)
                success = execute_query(query, params)
                if not success:
                    await interaction.followup.send("Alas the button is stuck, try again later.", ephemeral=True)
                    lock.release()
                    return
                
                result = success[0]
                latest_click_time_user = result[1]
                latest_click_time_overall = result[0].replace(tzinfo=timezone.utc)
                total_clicks = result[2]
                total_players = result[3]
                elapsed_time = (click_time - latest_click_time_overall).total_seconds()
                current_timer_value = max(game_session['timer_duration'] - elapsed_time, 0)
                color_state = get_color_state(current_timer_value)
                color_name = get_color_name(current_timer_value)
                
                if current_timer_value <= 0:
                    await interaction.followup.send("The game has already ended!", ephemeral=True)
                    lock.release()
                    return

                try:
                    if latest_click_time_user is not None:
                        latest_click_time_user = latest_click_time_user.replace(tzinfo=timezone.utc)
                        cooldown_remaining = int(((latest_click_time_user + datetime.timedelta(hours=6)) - click_time).total_seconds())
                        formatted_cooldown = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                        await interaction.followup.send(f'You have already clicked the button in the last 6 hours. Please try again in {formatted_cooldown}', ephemeral=True)
                        logger.info(f'Button click rejected. User {interaction.user} is on cooldown for {formatted_cooldown}')
                        current_expiration_end = latest_click_time_user + datetime.timedelta(hours=6)
                        display_name = interaction.user.display_name if interaction.user.display_name else interaction.user.name
                        user_manager.add_or_update_user(interaction.user.id, current_expiration_end, color_name, current_timer_value, display_name, game_id, latest_click_var=latest_click_time_user)
                        
                        lock.release()
                        return
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error processing button click: {e}, {tb}')
                    lock.release()
                    return
                
                query = 'INSERT INTO button_clicks (user_id, click_time, timer_value, game_id) VALUES (%s, %s, %s, %s)'
                params = (interaction.user.id, click_time, current_timer_value, game_id)
                success = execute_query(query, params, commit=True)
                if not success: 
                    logger.error(f'Failed to insert button click data. User: {interaction.user}, Timer Value: {current_timer_value}, Game ID: {game_session["game_id"]}')
                    lock.release()
                    return
                
                logger.info(f'Data inserted for {interaction.user}!')

                guild = interaction.guild
                timer_color_name = get_color_name(current_timer_value)
                color_role = nextcord.utils.get(guild.roles, name=timer_color_name)
                if color_role: await interaction.user.add_roles(color_role)

                # Confirm button click with user
                await interaction.followup.send("Button clicked! You have earned a " + timer_color_name + " click!", ephemeral=True)

                # Send button clicked message to game chat channel
                color_emoji = get_color_emoji(current_timer_value)
                #formatted_remaining_time = f"{format(int(current_timer_value//3600), '02d')} hours {format(int(current_timer_value%3600//60), '02d')} minutes and {format(round(int(current_timer_value%60), '02d'), 2)} seconds"
                current_timer_value = int(current_timer_value)
                formatted_remaining_time = f"{format(current_timer_value//3600, '02d')} hours {format(current_timer_value%3600//60, '02d')} minutes and {format(round(current_timer_value%60), '02d')} seconds"
                embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {timer_color_name} rank!", color=nextcord.Color.from_rgb(*color_state))
                chat_channel = bot.get_channel(game_session['game_chat_channel_id'])
                display_name = interaction.user.display_name
                if not display_name: display_name = interaction.user.name
                embed.description = f"{color_emoji}! {display_name} ({interaction.user.mention}), the {timer_color_name} rank warrior, has valiantly reset the timer with a mere {formatted_remaining_time} remaining! Let their bravery be celebrated throughout the realm!"
                await chat_channel.send(embed=embed)
                current_expiration_end = click_time + datetime.timedelta(hours=6)
                # Update user data
                user_manager.add_or_update_user(interaction.user.id, current_expiration_end, timer_color_name, current_timer_value, display_name, game_id)
                game_cache.update_game_cache(game_id, click_time, total_clicks, total_players, display_name)
                if paused_games and game_id in paused_games:
                    paused_games.remove(game_id)
                
                # Start the timer if it's not running
                if not update_timer.is_running():
                    logger.info('Starting update timer task...')
                    update_timer.start()
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error processing button click: {e}, {tb}')
                await interaction.followup.send("An error occurred while processing the button click.", ephemeral=True)
            finally:
                try:
                    lock.release()
                except:
                    pass
            task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
            logger.info(f'Callback run time: {task_run_time.total_seconds()} seconds')
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error processing button click: {e}, {tb}')

@bot.event
async def on_message(message):
    global cursor, db
    if message.author == bot.user and message.content.lower() != "sb": return
    if message.channel.id not in get_all_game_channels(): return
    
    logger.info(f"Message received in {message.guild.name}: {message.content}")
    try:
        await lock.acquire()
        if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
            logger.info(f"Starting button game in {message.guild.name}")
            if message.author.guild_permissions.administrator or message.author == bot.user:
                await message.channel.purge(limit=10, check=lambda m: m.author == bot.user)
                
                # purge in the last 5 messages if content is "sb" or "startbutton"
                async for m in message.channel.history(limit=5):
                    if m.author == bot.user and (m.content.lower() == "sb" or m.content.lower() == "startbutton"):
                        try:
                            await m.delete()
                        except:
                            pass
                
                game_session = get_game_session_by_guild_id(message.guild.id)
                if game_session:
                    await create_button_message(game_session['game_id'])
                    logger.info(f"Button game already started in {message.guild.name}")
                else:
                    logger.info(f"Starting button game in {message.guild.name}")
                    start_time = datetime.datetime.now(timezone.utc)
                    timer_duration = message.content.split(" ")[1] if len(message.content.split(" ")) > 2 else config['timer_duration']
                    cooldown_duration = message.content.split(" ")[2] if len(message.content.split(" ")) > 2 else config['cooldown_duration']
                    chat_channel_id = message.content.split(" ")[3] if len(message.content.split(" ")) > 3 else message.channel.id
                    
                    admin_role = nextcord.utils.get(message.guild.roles, name='Button Master')
                    if not admin_role:
                        admin_role = await message.guild.create_role(name='Button Master')
                        
                    if not admin_role in message.author.roles:
                        await message.author.add_roles(admin_role)
                        
                    game_id = create_game_session(admin_role.id, message.guild.id, message.channel.id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                    
                    game_session = get_game_session_by_id(game_id)
                    game_sessions_as_dict = game_sessions_dict()
                    if game_sessions_as_dict:
                        game_sessions_as_dict[game_id] = game_session
                    else:
                        update_local_game_sessions()
                        game_sessions_as_dict = game_sessions_dict()
                        game_sessions_as_dict = {game_id: game_session}
                    await setup_roles(message.guild.id)
                    await create_button_message(game_id)
                    update_local_game_sessions()
                    
                if not update_timer.is_running():
                    logger.info('Starting update timer task...')
                    update_timer.start()
            else:
                await message.channel.send('You do not have permission to start the button game.')
                
            try:
                await message.delete()
            except:
                pass
            
            

        elif message.content.lower() == 'myrank':
            is_other_user = False
            if len(message.content.split(" ")) > 1:
                user_check_id = int(message.content.split(" ")[1][3:-1])
                is_other_user = True
            else:
                user_check_id = message.author.id

            try:
                query = 'SELECT timer_value, click_time FROM button_clicks WHERE user_id = %s ORDER BY click_time'
                params = (user_check_id,)
                success = execute_query(query, params)
                if not success:
                    lock.release()
                    return

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
                    color_emojis = [get_color_emoji(
                        timer_value) for timer_value, _ in clicks]
                    color_counts = Counter(color_emojis)

                    total_claimed_time = sum(
                        config['timer_duration'] - timer_value for timer_value, _ in clicks)

                    emoji_sequence = ' '.join(color_emojis)
                    color_summary = ', '.join(
                        f'{emoji} x{count}' for emoji, count in color_counts.items())

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
            num_entries = 5
            if len(message.content.split()) > 1:
                try:
                    num_entries = int(message.content.split()[1])
                except ValueError:
                    pass
            try:
                query = '''
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
                '''
                success = execute_query(query)
                if not success: return
                most_clicks = cursor.fetchall()

                query = '''
                    SELECT user_name, timer_value
                    FROM button_clicks
                    ORDER BY timer_value
                    LIMIT 5
                '''
                success = execute_query(query, ())
                if not success: return
                lowest_individual_clicks = cursor.fetchall()

                query = '''
                    SELECT user_name, MIN(timer_value) AS lowest_click_time
                    FROM button_clicks
                    GROUP BY user_id
                    ORDER BY lowest_click_time
                    LIMIT 5
                '''
                success = execute_query(query, ())
                if not success: return
                lowest_user_clicks = cursor.fetchall()

                query = '''
                    SELECT
                        user_name,
                        SUM(43200 - timer_value) AS total_time_claimed
                    FROM button_clicks
                    GROUP BY user_id
                    ORDER BY total_time_claimed DESC
                    LIMIT %s
                '''
                success = execute_query(query, (num_entries,))
                if not success: return
                most_time_claimed = cursor.fetchall()

                embed = nextcord.Embed(
                    title='🏆 The Leaderboard Legends of the Button 🏆')

                top_clicks_value = '\n'.join(
                    f'{user.replace(".", "")}: {clicks} clicks ({" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)})'
                    for user, clicks, seq in most_clicks
                )
                embed.add_field(name='Mightiest Clickers (Most Clicks)',
                                value=top_clicks_value, inline=False)

                lowest_individual_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_individual_clicks
                )
                embed.add_field(name='Swiftest Clicks (Lowest Time When Clicked)',
                                value=lowest_individual_clicks_value, inline=False)

                lowest_user_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_user_clicks
                )
                embed.add_field(name='Nimblest Warriors (Lowest Time Clickers)',
                                value=lowest_user_clicks_value, inline=False)

                most_time_claimed_value = '\n'.join(
                    f'{user.replace(".", "")}: {format_time(time_claimed)}'
                    for user, time_claimed in most_time_claimed
                )
                embed.add_field(name='⌛ Temporal Titans (Most Time Claimed) ⌛',
                                value=most_time_claimed_value, inline=False)

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

            embed = nextcord.Embed(title='Help', description='How to use `myrank` and `leaderboard`')
            embed.add_field(name='myrank', value='Check your personal stats', inline=False)
            embed.add_field(name='leaderboard',value='Check the top 10 clickers', inline=False)
            embed.add_field(name='check', value='Check if you have a click ready', inline=False)
            embed.set_footer(text='May your clicks be swift and true, adventurer!')

            color = (106, 76, 147)
            embed.color = nextcord.Color.from_rgb(*color)
            await message.channel.send(embed=embed)

        elif message.content.lower() == 'check':
            user_check_id = message.author.id
            try:
                query = 'SELECT COUNT(*) AS click_count FROM button_clicks WHERE user_id = %s AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 6 HOUR)'
                params = (user_check_id,)
                success = execute_query(query, params)
                if not success:
                    logger.error('Failed to retrieve data.')
                    await message.add_reaction('❌')
                    return

                result = success[0]
                click_count = result[0]

                if click_count == 0:
                    response = "✅ Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. Go forth and claim your glory!"
                else:
                    response = "❌ Alas, noble warrior, you must rest and gather your strength. The button shall beckon you again when the time is right."

                embed = nextcord.Embed(description=response)
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                print(f'Error checking user cooldown: {e}, {tb}')
                logger.error(f'Error checking user cooldown: {e}, {tb}')
                await message.channel.send('An error occurred while checking your cooldown status.')

        elif message.content.lower() == 'lore':
            try:
                embed = nextcord.Embed(title="📜 __The Lore of The Button__ 📜", description=LORE_TEXT)
                embed.set_footer(text="⚡ *May your clicks be swift and true, adventurer!* ⚡")
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving lore: {e}, {tb}')
                await message.channel.send('❌ **An error occurred while retrieving the lore.** *The ancient archives seem to be temporarily sealed!* ❌')
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error processing message: {e}, {tb}')
    finally:
        logger.info('Releasing lock in on_message')
        lock.release()
        try:
            if db: db.close()
        except Exception as e:
            logger.error(f'Error closing database: {e}')
            pass
    

@bot.event
async def on_error(event, *args, **kwargs):
    if event == "on_message":
        print(f"Unhandled message: {args[0]}")
        logger.error(f"Unhandled message: {args[0]}")

    if isinstance(args[0], nextcord.HTTPException):
        if args[0].status == 429:
            retry_after = args[0].response.headers["Retry-After"]
            print(f"Rate limited. Retrying in {retry_after} seconds.")
            logger.warning(f"Rate limited. Retrying in {retry_after} seconds.")
            await asyncio.sleep(float(retry_after))
            return
    raise

@bot.event
async def on_ready():
    print(f"Starting bot... ")
    print(f"Initializing database pools...")
    if not setup_pool(): 
        print(f"Failed to initialize database pools.")
        logger.error(f"Failed to initialize database pools.")
        return 
    print(f"Database pools initialized.")
    print(f'Bot started as {bot.user}')
    logger.info(f'Bot started as {bot.user}')
    logger.info(f"Number of guilds: {len(bot.guilds)}")
    for guild in bot.guilds:
        logger.info(f'Connected to guild: {guild.name}')
        guild_id = guild.id
        game_session = get_game_session_by_guild_id(guild_id)
        if game_session:
            await setup_roles(guild_id)
            game_channel = bot.get_channel(game_session['button_channel_id'])
            if game_channel:
                await game_channel.send("sb")
                print(f"Sent sb to {game_channel.name}")
            else:
                logger.error(f"Button channel not found for game session {game_session['game_id']}")
        else:
            logger.info(f"No game session found for guild {guild.id}")
    logger.info(f'Bot ready!')  
    
@bot.event
async def on_disconnect():
    logger.info(f'Bot disconnected')
    close_disconnect_database()
    
async def close_bot():
    close_disconnect_database()
    await bot.close()
    exit(0)

async def terminate_handler(signal, frame):
    await asyncio.get_event_loop().run(close_bot())

signal.signal(signal.SIGINT, terminate_handler)

bot.run(config['discord_token'])

# try:
#     bot.run(config['discord_token'])
# except Exception as e:
#     close_disconnect_database()
#     logger.error(f'Error running bot: {e}')
# finally:
#     close_disconnect_database()
#     logger.info('Bot exited')
#     print('Bot exited')
    