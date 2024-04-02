import nextcord
from database.database import execute_query
from utils.utils import logger, lock, format_time

# Get end game embed
# This function gets the data for the entire game session and creates an embed to display the results.
# The embed includes the total number of clicks, the duration of the game, the number of participants, the most active participant, the longest timer reached, and the color click distribution.
def get_end_game_embed(game_session_id, guild):
    global lock
    embed = nextcord.Embed(title='The Button Game', description='Game Ended!')

    query = 'SELECT COUNT(*) FROM button_clicks WHERE game_id = %s'
    params = (game_session_id,)
    with lock: total_clicks = execute_query(query, params)
    if total_clicks is not None:
        total_clicks = total_clicks[0][0]
        embed.add_field(name='Total Button Clicks', value=str(total_clicks), inline=False)
    else:
        logger.error('Failed to retrieve total clicks.')
        return

    query = 'SELECT MIN(click_time), MAX(click_time) FROM button_clicks WHERE game_id = %s'
    params = (game_session_id,)
    with lock: result = execute_query(query, params)
    if result is not None:
        start_time, end_time = result[0]
        duration = end_time - start_time
        embed.add_field(name='Game Duration', value=str(duration), inline=False)
    else:
        logger.error('Failed to retrieve game duration.')
        return

    query = 'SELECT COUNT(DISTINCT user_id) FROM button_clicks WHERE game_id = %s'
    params = (game_session_id,)
    with lock: num_participants = execute_query(query, params)
    
    if num_participants is not None:
        num_participants = num_participants[0][0]
        embed.add_field(name='Number of Participants', value=str(num_participants), inline=False)
    else:
        logger.error('Failed to retrieve number of participants.')
        return

    query = '''
        SELECT users.user_name, COUNT(*) AS click_count
        FROM button_clicks
        JOIN users ON button_clicks.user_id = users.user_id
        WHERE button_clicks.game_id = %s
        GROUP BY users.user_id
        ORDER BY click_count DESC
        LIMIT 1
    '''
    params = (game_session_id,)
    with lock: most_active = execute_query(query, params)
    if most_active is not None:
        embed.add_field(name='Most Active Participant', value=f"{most_active[0][0]} ({most_active[0][1]} clicks)", inline=False)
    else:
        logger.error('Failed to retrieve most active participant.')
        return

    query = 'SELECT MAX(timer_value) FROM button_clicks WHERE game_id = %s'
    params = (game_session_id,)
    with lock: longest_timer = execute_query(query, params)
    if longest_timer is not None:
        longest_timer = longest_timer[0][0]
        embed.add_field(name='Longest Timer Reached', value=format_time(longest_timer), inline=False)
    else:
        logger.error('Failed to retrieve longest timer.')
        return

    color_distribution = []
    for color in ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple']:
        role = nextcord.utils.get(guild.roles, name=color)
        if role is not None:
            count = len(role.members)
            color_distribution.append(f"- {color}: {count}")
    embed.add_field(name='Color Click Distribution', value='\n'.join(color_distribution), inline=False)

    return embed