import nextcord
import traceback
from database.database import execute_query
from utils.utils import logger, lock, format_time
import os

# Get end game embed
# This function gets the data for the entire game session and creates an embed to display the results.
# The embed includes the total number of clicks, the duration of the game, the number of participants, the most active participant, and the color click distribution.
def get_end_game_embed(game_session_id, guild):
    try:
        embed = nextcord.Embed(title='The Button Game', description='Game Ended!')

        query = 'SELECT COUNT(*) FROM button_clicks WHERE game_id = %s'
        params = (game_session_id,)
        total_clicks = execute_query(query, params)
        if total_clicks is not None and total_clicks[0]:
            total_clicks = total_clicks[0][0]
            embed.add_field(name='Total Button Clicks', value=str(total_clicks), inline=False)
        else:
            logger.warning(f'No clicks found for game {game_session_id}')
            embed.add_field(name='Total Button Clicks', value='0', inline=False)

        query = 'SELECT MIN(click_time), MAX(click_time) FROM button_clicks WHERE game_id = %s'
        params = (game_session_id,)
        result = execute_query(query, params)
        if result is not None and result[0] and result[0][0] is not None and result[0][1] is not None:
            start_time, end_time = result[0]
            duration = end_time - start_time
            embed.add_field(name='Game Duration', value=str(duration), inline=False)
        else:
            logger.warning(f'No valid click times found for game {game_session_id}')
            # Fallback to game session times
            session_query = 'SELECT start_time, end_time FROM game_sessions WHERE id = %s'
            session_result = execute_query(session_query, (game_session_id,))
            if session_result and session_result[0] and session_result[0][0] and session_result[0][1]:
                start_time, end_time = session_result[0]
                duration = end_time - start_time
                embed.add_field(name='Game Duration', value=str(duration), inline=False)
            else:
                embed.add_field(name='Game Duration', value='Unknown', inline=False)

        query = 'SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = %s'
        params = (game_session_id,)
        num_participants = execute_query(query, params)
        
        if num_participants is not None and num_participants[0]:
            num_participants = num_participants[0][0]
            embed.add_field(name='Number of Participants', value=str(num_participants), inline=False)
        else:
            logger.warning(f'No participants found for game {game_session_id}')
            embed.add_field(name='Number of Participants', value='0', inline=False)

        # Get timer duration for proper color calculations
        timer_duration_query = 'SELECT timer_duration FROM game_sessions WHERE id = %s'
        timer_duration_result = execute_query(timer_duration_query, (game_session_id,))
        timer_duration = 43200  # Default 12 hours
        if timer_duration_result and timer_duration_result[0] and timer_duration_result[0][0]:
            timer_duration = timer_duration_result[0][0]

        # Top 5 Most Active Players
        query = '''
            SELECT users.user_name, COUNT(*) AS click_count
            FROM button_clicks
            JOIN users ON button_clicks.user_id = users.user_id
            WHERE button_clicks.game_id = %s
            GROUP BY users.user_id
            ORDER BY click_count DESC
            LIMIT 5
        '''
        params = (game_session_id,)
        top_clickers = execute_query(query, params)
        if top_clickers is not None and len(top_clickers) > 0:
            clickers_text = ""
            for i, (username, clicks) in enumerate(top_clickers, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                clickers_text += f"{medal} {username}: {clicks} clicks\n"
            embed.add_field(name='🏆 Most Active Players', value=clickers_text, inline=False)
        else:
            embed.add_field(name='🏆 Most Active Players', value='None', inline=False)

        # Top 5 Fastest Clicks
        query = '''
            SELECT users.user_name, MIN(button_clicks.timer_value) AS fastest_click
            FROM button_clicks
            JOIN users ON button_clicks.user_id = users.user_id
            WHERE button_clicks.game_id = %s
            GROUP BY users.user_id
            ORDER BY fastest_click ASC
            LIMIT 5
        '''
        params = (game_session_id,)
        fastest_clickers = execute_query(query, params)
        if fastest_clickers is not None and len(fastest_clickers) > 0:
            fastest_text = ""
            for i, (username, fastest_time) in enumerate(fastest_clickers, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                fastest_text += f"{medal} {username}: {format_time(fastest_time)}\n"
            embed.add_field(name='⚡ Fastest Clicks', value=fastest_text, inline=False)
        else:
            embed.add_field(name='⚡ Fastest Clicks', value='None', inline=False)

        # Top 5 Time Savers
        query = '''
            SELECT 
                users.user_name,
                SUM(GREATEST(0, %s - button_clicks.timer_value)) AS total_time_claimed
            FROM button_clicks
            JOIN users ON button_clicks.user_id = users.user_id
            WHERE button_clicks.game_id = %s
            GROUP BY users.user_id
            ORDER BY total_time_claimed DESC
            LIMIT 5
        '''
        params = (timer_duration, game_session_id)
        time_savers = execute_query(query, params)
        if time_savers is not None and len(time_savers) > 0:
            savers_text = ""
            for i, (username, time_saved) in enumerate(time_savers, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                savers_text += f"{medal} {username}: {format_time(time_saved)}\n"
            embed.add_field(name='⏰ Time Savers', value=savers_text, inline=False)
        else:
            embed.add_field(name='⏰ Time Savers', value='None', inline=False)

        # Color click distribution based on actual timer_duration and 6 color segments
        query = '''
            SELECT 
                CASE
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                    ELSE 'Purple'
                END as color_name,
                COUNT(*) as click_count
            FROM button_clicks
            WHERE game_id = %s
            GROUP BY 
                CASE
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 16.67 THEN 'Red'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 33.33 THEN 'Orange'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 50.00 THEN 'Yellow'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 66.67 THEN 'Green'
                    WHEN ROUND((timer_value / %s) * 100, 2) <= 83.33 THEN 'Blue'
                    ELSE 'Purple'
                END
            ORDER BY MIN(ROUND((timer_value / %s) * 100, 2)) ASC
        '''
        params = (timer_duration, timer_duration, timer_duration, timer_duration, timer_duration, 
                 game_session_id, timer_duration, timer_duration, timer_duration, timer_duration, 
                 timer_duration, timer_duration)
        color_distribution_result = execute_query(query, params)

        color_distribution = []
        color_emojis = {
            'Red': '🔴',
            'Orange': '🟠',
            'Yellow': '🟡',
            'Green': '🟢',
            'Blue': '🔵',
            'Purple': '🟣'
        }
        
        if color_distribution_result:
            for color_name, count in color_distribution_result:
                emoji = color_emojis.get(color_name, '⚪')
                color_distribution.append(f"{emoji} {color_name}: {count}")
        else:
            color_distribution = ["No color data available"]
            
        embed.add_field(name='🎨 Color Click Distribution', value='\n'.join(color_distribution), inline=False)

        # Fix the image path - use absolute path to /app/assets/
        image_path = "/app/assets/end_game.png"
        if not os.path.exists(image_path):
            logger.warning(f"Image file not found: {image_path}")
            file = None
        else:
            file = nextcord.File(image_path, filename='end_game.png')
            embed.set_image(url='attachment://end_game.png')
            
        embed.set_footer(text='Game Ended! Thank you for playing The Button Game!')
        return embed, file
        
    except Exception as e:
        logger.error(f"Error in get_end_game_embed: {e}")
        logger.error(traceback.format_exc())
        return None, None