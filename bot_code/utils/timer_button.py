# Timer Button
import nextcord
import datetime
import asyncio
import traceback
import random
from datetime import timezone

# Local imports
from utils.utils import logger, lock, get_color_state, get_color_name, get_color_emoji
from user.user_manager import user_manager
from button.button_utils import get_button_message, Failed_Interactions
from game.game_cache import game_cache
from database.database import execute_query, get_game_session_by_guild_id, get_game_session_by_id

# TimerButton class for the button with Nextcord UI
# This class is used to create a button that resets the timer when clicked.
# The callback method is called when the button is clicked, updating the timer and the database with the new timer value.
# The timer value is passed as a parameter to the class, which is the time remaining on the timer when the button is clicked.
# Checks for cooldowns and prevents users from clicking the button within the cooldown period.
# Updates the user's color rank and adds a role to the user based on the timer value.
# Sends an announcement message to the game chat channel when the button is clicked.
class TimerButton(nextcord.ui.Button):
    def __init__(self, bot, style=nextcord.ButtonStyle.primary, label="Click me!", timer_value=0, game_id=None):
        # Initialize with a custom_id based on game_id for persistence
        custom_id = f"button_game_{game_id}" if game_id else None
        super().__init__(style=style, label=label, custom_id=custom_id)
        self.bot = bot
        self.timer_value = timer_value
        self.game_id = game_id

    # Callback method for the button, called when the button is clicked
    async def callback(self, interaction: nextcord.Interaction):
        global game_cache
        try:
            # First attempt with standard defer
            try:
                logger.info(f"Button clicked by {interaction.user.id} - Component ID: {self.custom_id}")
                await interaction.response.defer(ephemeral=True)
            except nextcord.errors.NotFound:
                logger.warning(f"Initial interaction defer failed for user {interaction.user.id}. Attempting recovery...")
                # Short sleep to allow for potential race condition resolution
                await asyncio.sleep(0.5)
                try:
                    # Attempt direct message send as fallback
                    await interaction.followup.send("Processing your click...", ephemeral=True)
                except nextcord.errors.NotFound as e:
                    logger.error(f"Complete interaction failure for user {interaction.user.id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    Failed_Interactions.increment()
                    return
            except Exception as e:
                logger.error(f"Unexpected error in interaction recovery: {str(e)}")
                logger.error(traceback.format_exc())
                Failed_Interactions.increment()
                return
            
            # Followup with user that the click is being processed
            await interaction.followup.send("You attempt a click...", ephemeral=True)
            click_time = task_run_time = datetime.datetime.now(timezone.utc)
            
            try:
                # Get the game session and button message
                game_session = get_game_session_by_guild_id(interaction.guild.id)
                game_id = game_session['game_id']
                timer_duration = game_session['timer_duration']
                cooldown_duration = game_session['cooldown_duration']
                
                # Debug log the current state
                logger.info(f"Processing click for game {game_id} at {click_time}")
                cached_game = game_cache.get_game_cache(game_id)
                if cached_game:
                    logger.info(f"Cache state - Last click: {cached_game['latest_click_time']}, Timer value: {cached_game['last_timer_value']}")
                
                button_message = await get_button_message(game_id, self.bot)
                embed = button_message.embeds[0]
                user_id = interaction.user.id
                
                is_expired, current_timer_value = is_timer_expired(game_id)
                
                if is_expired:
                    logger.error(f"Game {game_id} timer expired: {current_timer_value}")
                    await interaction.followup.send("The timer has expired! Game over!", ephemeral=True)
                    return
                    
                logger.info(f"Processing click with timer value: {current_timer_value}")

                # Check if the user is on cooldown and alert them if they are, since the cache was not used, and therefore the database data must be checked
                try:
                    # Check if the user is on cooldown
                    query = '''
                        SELECT MAX(click_time)
                        FROM button_clicks
                        WHERE user_id = %s
                        AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s HOUR)
                    '''
                    params = (interaction.user.id, cooldown_duration)
                    result = execute_query(query, params)
                    
                    if result and result[0][0] is not None:
                        latest_click_time_user = result[0][0].replace(tzinfo=timezone.utc)
                        cooldown_remaining = int(((latest_click_time_user + datetime.timedelta(hours=cooldown_duration)) - click_time).total_seconds())
                        formatted_cooldown = f"{format(int(cooldown_remaining//3600), '02d')}:{format(int(cooldown_remaining%3600//60), '02d')}:{format(int(cooldown_remaining%60), '02d')}"
                        await interaction.followup.send(f'You have already clicked the button in the last {cooldown_duration} hours. Please try again in {formatted_cooldown}', ephemeral=True)
                        logger.info(f'Button click rejected. User {interaction.user} is on cooldown for {formatted_cooldown}')
                        current_expiration_end = latest_click_time_user + datetime.timedelta(hours=cooldown_duration)
                        display_name = interaction.user.display_name
                        if not display_name:
                            display_name = interaction.user.name
                        return
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error processing cooldown check: {e}, {tb}')
                    return

                await interaction.message.add_reaction("⏳")

                # Insert the button click data into the database
                query = 'INSERT INTO button_clicks (user_id, click_time, timer_value, game_id) VALUES (%s, %s, %s, %s)'
                params = (interaction.user.id, click_time, current_timer_value, game_id)
                success = execute_query(query, params, commit=True)
                if not success: logger.error(f'Failed to insert button click data. User: {interaction.user}, Timer Value: {current_timer_value}, Game ID: {game_session["game_id"]}'); return
                logger.info(f'Data inserted for {interaction.user}!')

                # Update the user's color rank and add the role to the user
                guild = interaction.guild
                timer_color_name = get_color_name(current_timer_value, timer_duration)
                color_role = nextcord.utils.get(guild.roles, name=timer_color_name)
    
                if color_role:
                    try:
                        await interaction.user.add_roles(color_role)
                        logger.info(f'Role added to {interaction.user}: {color_role.name}')
                    except nextcord.errors.Forbidden:
                        logger.error(f'Failed to add role to {interaction.user}: {color_role.name}')
                        pass
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error while adding role to {interaction.user}: {e}, {tb}')
                        pass
                
                await interaction.followup.send("Button clicked! You have earned a " + timer_color_name + " click!", ephemeral=True)

                # Create an embed message that announces the button click in the game chat channel
                color_emoji = get_color_emoji(current_timer_value, timer_duration)
                current_timer_value = int(current_timer_value)
                formatted_remaining_time = f"{format(current_timer_value//3600, '02d')} hours {format(current_timer_value%3600//60, '02d')} minutes and {format(round(current_timer_value%60), '02d')} seconds"
                color_state = get_color_state(current_timer_value, timer_duration)
                embed = nextcord.Embed(title="", description=f"{color_emoji} {interaction.user.mention} just reset the timer at {formatted_remaining_time} left, for {timer_color_name} rank!", color=nextcord.Color.from_rgb(*color_state))
                chat_channel = self.bot.get_channel(game_session['game_chat_channel_id'])
                display_name = interaction.user.display_name
                if not display_name: display_name = interaction.user.name
                embed.description = f"{color_emoji}! {display_name} ({interaction.user.mention}), the {timer_color_name} rank warrior, has valiantly reset the timer with a mere {formatted_remaining_time} remaining!\nLet their bravery be celebrated throughout the realm!"

                # We now append one of ten random positive affirmation messages to the embed description
                affirmations = [
                    "That was a great click! Keep it up!",
                    "You're doing amazing! Keep going!",
                    "You're a star! Keep shining!",
                    "DAMN that was a good click! WOOT WOOT!",
                    "Now that's what I call a click!",
                    "That one felt lucky!!",
                    "THE BUTTON HAS BEEN CLICKED! LFG!"
                ]
                affirmation = random.choice(affirmations)
                embed.description += f"\n\n{affirmation}"

                await chat_channel.send(embed=embed)
                # cooldown_duration = game_session['cooldown_duration']
                # current_expiration_end = click_time + datetime.timedelta(hours=cooldown_duration)
                
                with lock:
                    #user_manager.add_or_update_user(interaction.user.id, current_expiration_end, timer_color_name, current_timer_value, display_name, game_id, latest_click_var=click_time)
                    game_cache.update_game_cache(game_id, click_time, None, None, display_name, current_timer_value)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error 1 processing button click: {e}, {tb}')
                await interaction.followup.send("Fuck! Something went wrong. Please try again later.", ephemeral=True)
            task_run_time = datetime.datetime.now(timezone.utc) - task_run_time
            logger.info(f'Callback run time: {task_run_time.total_seconds()} seconds')

            # Use AI to generate a positive affirmation message!
            # Details:
            # - Utilize another discord bot called JuwuL. Guilde 1082416982537797672 channel 1314720128868417588.
            # - Send a message to the channel with the user's name and the timer color name.
            # - The bot will respond with a positive affirmation message.
            # - The message will be sent to the user in the chat channel.
            # try:
            #     affirmation_channel = self.bot.get_channel(1314720128868417588)
            #     if affirmation_channel:
            #         await affirmation_channel.send(f"{display_name} just clicked the button and earned a {timer_color_name} click at {formatted_remaining_time} left in the game! They are from the guild {interaction.guild.name}.")
            #         # Wait for JuwuL's response
    
            #         await asyncio.sleep(5)
                    
            #         affirmation_message = None
            #         while True:
            #             try:
            #                 msg = await affirmation_channel.history(limit=5).flatten()[0]
            #                 if msg.content:
            #                     affirmation_message = msg
            #                     break
            #             except asyncio.TimeoutError:
            #                 logger.warning("Timeout waiting for JuwuL response")
            #                 # Check if last message was sent by JuwuL
    

            #                 break
            #             await asyncio.sleep(0.5)

                    
            #         if affirmation_message:
            #             affirmation_message = affirmation_message[0].content
            #             await chat_channel.send(affirmation_message)
            #         else:
            #             logger.warning("No affirmation message received from JuwuL")
            #     else:
            #         logger.warning("No affirmation message received from JuwuL")
            # except Exception as e:
            #     tb = traceback.format_exc()
            #     logger.error(f'Error sending affirmation message: {e}, {tb}')
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error 2 processing button click: {e}, {tb}')


def is_timer_expired(game_id):
    try:
        query = '''
            SELECT click_time, timer_value
            FROM button_clicks 
            WHERE game_id = %s
            ORDER BY click_time DESC
            LIMIT 1
        '''
        result = execute_query(query, (game_id,))
        
        if not result or not result[0]:
            game_session = get_game_session_by_id(game_id)
            return False, game_session['timer_duration']
            
        last_click_time, timer_value = result[0]
        current_time = datetime.datetime.now(timezone.utc)
        elapsed_time = (current_time - last_click_time.replace(tzinfo=timezone.utc)).total_seconds()
        
        # Use the full timer_duration from game_session as the start point
        game_session = get_game_session_by_id(game_id)
        current_timer = max(0, float(game_session['timer_duration']) - elapsed_time)
        
        return current_timer <= 0, current_timer
        
    except Exception as e:
        logger.error(f"Error checking timer expiration: {e}")
        logger.error(traceback.format_exc())
        return True, 0