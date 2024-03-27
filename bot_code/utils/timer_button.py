# Timer Button
import nextcord
import datetime
import asyncio
import traceback
from datetime import timezone

from utils.utils import *
from user.user_manager import user_manager
from button.button_utils import get_button_message, Failed_Interactions
from game.game_cache import game_cache
from database.database import execute_query, get_game_session_by_guild_id

class TimerButton(nextcord.ui.Button):
    def __init__(self, bot, style=nextcord.ButtonStyle.primary, label="Click me!", timer_value=0):
        super().__init__(style=style, label=label)
        self.bot = bot
        self.timer_value = timer_value

    async def callback(self, interaction: nextcord.Interaction):
        global game_cache
        try:
            await interaction.response.defer(ephemeral=True)
        except nextcord.errors.NotFound:
            logger.warning("Interaction not found. Retrying...")
            await asyncio.sleep(1)
            try:
                await interaction.send("Adventurer! You attempt to click the button...", ephemeral=True)
            except nextcord.errors.NotFound:
                Failed_Interactions.increment()
                return
        
        task_run_time = datetime.datetime.now(timezone.utc)
        try:
            click_time = datetime.datetime.now(timezone.utc)
            
            try:
                game_session = get_game_session_by_guild_id(interaction.guild.id)
                game_id = game_session['game_id']
                button_message = await get_button_message(game_id, self.bot)
                embed = button_message.embeds[0]
                user_id = interaction.user.id
                if user_id is None:
                    logger.error(f'User ID is None for interaction {interaction}')
                    return
                
                user_data = user_manager.get_user_from_cache(user_id=user_id)
                if user_data is not None:
                    latest_click_time_user, cooldown_expiration = None, None
                    cooldown_expiration = user_data['cooldown_expiration']
                    latest_click_time_user = user_data['latest_click_time']
                    
                    if cooldown_expiration is not None:
                        cooldown_remaining = int((cooldown_expiration - click_time).total_seconds())
                        if cooldown_remaining > 0:
                            formatted_cooldown = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                            await interaction.followup.send(f'You have already clicked the button in the last 6 hours. Please try again in {formatted_cooldown}', ephemeral=True)
                            logger.info(f'Button click rejected. User {interaction.user} is on cooldown for {formatted_cooldown}')
                            current_expiration_end = latest_click_time_user + datetime.timedelta(hours=6)
                            display_name = interaction.user.display_name
                            if not display_name: display_name = interaction.user.name
                            await lock.acquire()
                            user_manager.add_or_update_user(interaction.user.id, current_expiration_end, user_data['color_rank'], user_data['timer_value'], display_name, user_data['game_id'])
                            lock.release()
                            return
                
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
                    return

                try:
                    if latest_click_time_user is not None:
                        latest_click_time_user = latest_click_time_user.replace(tzinfo=timezone.utc)
                        cooldown_remaining = int(((latest_click_time_user + datetime.timedelta(hours=6)) - click_time).total_seconds())
                        formatted_cooldown = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                        await interaction.followup.send(f'You have already clicked the button in the last 6 hours. Please try again in {formatted_cooldown}', ephemeral=True)
                        logger.info(f'Button click rejected. User {interaction.user} is on cooldown for {formatted_cooldown}')
                        current_expiration_end = latest_click_time_user + datetime.timedelta(hours=6)
                        display_name = interaction.user.display_name
                        if not display_name: display_name = interaction.user.name
                        await lock.acquire()
                        user_manager.add_or_update_user(interaction.user.id, current_expiration_end, color_name, current_timer_value, display_name, game_id, latest_click_var=latest_click_time_user)
                        lock.release()
                        return
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error processing button click: {e}, {tb}')
                    return
                
                await lock.acquire()
                query = 'INSERT INTO button_clicks (user_id, click_time, timer_value, game_id) VALUES (%s, %s, %s, %s)'
                params = (interaction.user.id, click_time, current_timer_value, game_id)
                success = execute_query(query, params, commit=True)
                if not success: 
                    logger.error(f'Failed to insert button click data. User: {interaction.user}, Timer Value: {current_timer_value}, Game ID: {game_session["game_id"]}')
                    lock.release()
                    return
                
                lock.release()
                logger.info(f'Data inserted for {interaction.user}!')

                guild = interaction.guild
                timer_color_name = get_color_name(current_timer_value)
                color_role = nextcord.utils.get(guild.roles, name=timer_color_name)
                if color_role: await interaction.user.add_roles(color_role)

                await interaction.followup.send("Button clicked! You have earned a " + timer_color_name + " click!", ephemeral=True)

                color_emoji = get_color_emoji(current_timer_value)
                current_timer_value = int(current_timer_value)
                formatted_remaining_time = f"{format(current_timer_value//3600, '02d')} hours {format(current_timer_value%3600//60, '02d')} minutes and {format(round(current_timer_value%60), '02d')} seconds"
                embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {timer_color_name} rank!", color=nextcord.Color.from_rgb(*color_state))
                
                chat_channel = self.bot.get_channel(game_session['game_chat_channel_id'])
                
                display_name = interaction.user.display_name
                if not display_name: display_name = interaction.user.name
                
                embed.description = f"{color_emoji}! {display_name} ({interaction.user.mention}), the {timer_color_name} rank warrior, has valiantly reset the timer with a mere {formatted_remaining_time} remaining!\nLet their bravery be celebrated throughout the realm!"
                await chat_channel.send(embed=embed)
                current_expiration_end = click_time + datetime.timedelta(hours=6)
                
                await lock.acquire()
                user_manager.add_or_update_user(interaction.user.id, current_expiration_end, timer_color_name, current_timer_value, display_name, game_id, latest_click_var=click_time)
                game_cache.update_game_cache(game_id, click_time, total_clicks, total_players, display_name, current_timer_value)
                lock.release()
                
                from theButton import menu_timer
                if not menu_timer.update_timer_task.is_running():
                    logger.info('Starting update timer task...')
                    menu_timer.update_timer_task.start()
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
