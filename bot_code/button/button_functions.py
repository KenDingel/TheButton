# Button Functions
import nextcord
from nextcord.ext import tasks
from bot_code.utils.utils import *
from bot_code.game.game_cache import *
from bot_code.database.database import *
from bot_code.text.full_text import *
from bot_code.game.end_game import get_end_game_embed
from bot_code.button.button_utils import get_button_message, Failed_Interactions

async def setup_roles(guild_id, bot):
    guild = bot.get_guild(guild_id)
    for color_name, color_value in zip(['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple'], COLOR_STATES):
        role = nextcord.utils.get(guild.roles, name=color_name)
        if role is None:
            role = await guild.create_role(name=color_name, color=nextcord.Color.from_rgb(*color_value))
        else:
            await role.edit(color=nextcord.Color.from_rgb(*color_value))
    logger.info(f"In {guild.name}, roles have been set up.")

async def create_button_message(game_id, bot):
    logger.info(f'Creating button message for game {game_id}...')
    try:
        game_session_config = get_game_session_by_id(game_id)
        embed = nextcord.Embed(title='🚨 THE BUTTON! 🚨', description='**Keep the button alive!**')
        button_channel = bot.get_channel(game_session_config['button_channel_id'])
        async for message in button_channel.history(limit=15):
            if message.author == bot.user and message.embeds:
                await message.delete()
                
        if not EXPLAINATION_TEXT in [msg.content async for msg in button_channel.history(limit=2)]:
            await bot.get_channel(game_session_config['button_channel_id']).send(EXPLAINATION_TEXT)
        
        from bot_code.button.button_view import ButtonView
        message = await button_channel.send(embed=embed, view=ButtonView(game_session_config['timer_duration'], bot))
        button_message_cache.update_message_cache(message, game_id)
        return message
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error creating button message: {e}, {tb}')
        return None

paused_games = []

class MenuTimer(nextcord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        
    @tasks.loop(seconds=10)
    async def update_timer_task(self):
        global lock, paused_games, game_cache
        failed_count = Failed_Interactions.get()
        for game_id, game_session in game_sessions_dict().items():
            if paused_games and game_id in paused_games:
                logging.info(f'Game {game_id} is paused, skipping...')
                continue
            
            if failed_count > 5:
                await self.bot.get_channel(game_session['button_channel_id']).send('sb')
                await asyncio.sleep(10)
                
            game_id = str(game_id)
            try:
                cache_data = game_cache.get_game_cache(game_id)
                last_update_time = None
                if cache_data:
                    latest_click_time_overall = cache_data['latest_click_time']
                    total_clicks = cache_data['total_clicks']
                    last_update_time = cache_data['last_update_time']
                    total_players = cache_data['total_players']
                    user_name = cache_data['latest_player_name']
                    last_timer_value = cache_data['last_timer_value']
                else:
                    query = f'''
                        SELECT users.user_name, button_clicks.click_time, button_clicks.timer_value,
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
                    user_name, latest_click_time_overall, last_timer_value, total_clicks, total_players = result
                    latest_click_time_overall = latest_click_time_overall.replace(tzinfo=timezone.utc) if latest_click_time_overall.tzinfo is None else latest_click_time_overall
                    last_update_time = datetime.datetime.now(timezone.utc)
                    game_cache.update_game_cache(game_id, latest_click_time_overall, total_clicks, total_players, user_name, last_timer_value)
                    
                elapsed_time = (datetime.datetime.now(timezone.utc) - latest_click_time_overall).total_seconds()
                timer_value = max(game_session['timer_duration'] - elapsed_time, 0)

                if last_update_time is None or not last_update_time:
                    last_update_time = datetime.datetime.now(timezone.utc)
                
                if datetime.datetime.now(timezone.utc) - last_update_time > datetime.timedelta(minutes=15):
                    logger.info(f'Clearing cache for game {game_id}, since last update was more than 15 minutes ago...')
                    game_cache.clear_game_cache(game_id)
                
                color_name = get_color_name(last_timer_value)
                color_emoji = get_color_emoji(last_timer_value)
                hours_remaining = int(last_timer_value) // 3600
                minutes_remaining = int(last_timer_value) % 3600 // 60
                seconds_remaining = int(int(last_timer_value) % 60)
                formatted_timer_value = f'{hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}'
                formatted_time = f'<t:{int(latest_click_time_overall.timestamp())}:R>'
                latest_user_info = f'{formatted_time} {user_name} clicked {color_emoji} {color_name} with {formatted_timer_value} left on the clock!'
                button_message = await get_button_message(game_id, self.bot)
                try:
                    embed = button_message.embeds[0]
                except AttributeError:
                    logger.error(f'No embed found for game {game_id}, creating a new one...')
                    button_message = await create_button_message(game_id, self.bot)
                    embed = button_message.embeds[0]
                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f'Error getting button message: {e}, {tb}')
                    return
                
                if timer_value <= 0:
                    embed = get_end_game_embed(game_id)
                    await button_message.edit(embed=embed)
                    self.update_timer_task.stop()
                    logger.info(f'Game {game_id} Ended!')
                else:
                    embed.title = '🚨 THE BUTTON! 🚨'
                    embed.description = '**Keep the button alive!**'
                    embed.clear_fields()
                    
                    start_time = game_session['start_time'].replace(tzinfo=timezone.utc)
                    elapsed_time = datetime.datetime.now(timezone.utc) - start_time

                    elapsed_days = elapsed_time.days
                    elapsed_hours = elapsed_time.seconds // 3600
                    elapsed_minutes = (elapsed_time.seconds % 3600) // 60
                    elapsed_seconds = elapsed_time.seconds % 60
                    elapsed_seconds = round(elapsed_seconds, 2)
                    elapsed_time_str = f'{elapsed_days} days, {elapsed_hours} hours, {elapsed_minutes} minutes, {elapsed_seconds} seconds'

                    embed.add_field(name='🗺️ The Saga Unfolds', value=f'Valiant clickers in the pursuit of glory, have kept the button alive for...\n**{elapsed_time_str}**!\n**{total_clicks} clicks** have been made by **{total_players} adventurers**! 🛡️🗡️🏰', inline=False)
                    embed.add_field(name='🎉 Latest Heroic Click', value=latest_user_info, inline=False)
                    note = "Brave adventurers, a temporary disruption occurred, you may need to click the button again if fails to be pushed."
                    embed.add_field(name='📣 Proclamation from the Button Guardians', value=note, inline=False)
                    embed.description = f'__The game ends when the timer hits 0__.\nClick the button to reset the clock and keep the game going!\n\nWill you join the ranks of the brave and keep the button alive? 🛡️🗡️'
                    embed.set_footer(text=f'The Button Game by Regen2Moon; Inspired by Josh Wardle')
                    file_buffer = generate_timer_image(timer_value)
                    embed.set_image(url=f'attachment://{file_buffer.filename}')
                    pastel_color = get_color_state(timer_value)
                    embed.color = nextcord.Color.from_rgb(*pastel_color)
                    
                    from bot_code.button.button_view import ButtonView
                    button_view = ButtonView(timer_value, self.bot)
                    await button_message.edit(embed=embed, file=file_buffer, view=button_view)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error updating timer: {e}, {tb}')
                
    @update_timer_task.before_loop
    async def before_update_timer(self):
        await self.bot.wait_until_ready()

    async def on_timeout(self):
        self.update_timer_task.cancel()