import nextcord
from database import execute_query
from utils import logger, format_time

def get_end_game_embed(game_session_id):
    
    embed = nextcord.Embed(title='The Button Game', description='Game Ended!')

    query = 'SELECT COUNT(*) FROM button_clicks'
    params = ()
    success, total_clicks = execute_query(query, params)
    if success:
        print('Data retrieved successfully!')
    else:
        print('Failed to retrieve data.')
        logger.error('Failed to retrieve data.')
        return
    embed.add_field(name='Total Button Clicks',
                    value=str(total_clicks), inline=False)

    query = 'SELECT MIN(click_time), MAX(click_time) FROM button_clicks'
    params = ()
    success, result = execute_query(query, params)
    if success:
        start_time, end_time = result[0], result[1]
    else:
        print('Failed to retrieve data.')
        logger.error('Failed to retrieve data.')
        return
    duration = end_time - start_time
    embed.add_field(name='Game Duration',
                    value=str(duration), inline=False)

    query = 'SELECT COUNT(DISTINCT user_id) FROM button_clicks'
    params = ()
    success, num_participants = execute_query(query, params)
    if success:
        print('Data retrieved successfully!')
    else:
        print('Failed to retrieve data.')
        logger.error('Failed to retrieve data.')
        return
    embed.add_field(name='Number of Participants',
                    value=str(num_participants), inline=False)

    query = 'SELECT user_name, COUNT(*) AS click_count FROM button_clicks GROUP BY user_id ORDER BY click_count DESC LIMIT 1'
    params = ()
    success, most_active = execute_query(query, params)
    if success:
        print('Data retrieved successfully!')
    else:
        print('Failed to retrieve data.')
        logger.error('Failed to retrieve data.')
        return
    embed.add_field(name='Most Active Participant',
                    value=f"{most_active[0]} ({most_active[1]} clicks)", inline=False)

    query = 'SELECT MAX(timer_value) FROM button_clicks'
    params = ()
    success, longest_timer = execute_query(query, params)
    if success:
        print('Data retrieved successfully!')
    else:
        print('Failed to retrieve data.')
        logger.error('Failed to retrieve data.')
        return
    embed.add_field(name='Longest Timer Reached',
                    value=format_time(longest_timer), inline=False)

    color_distribution = []
    for color in ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple']:
        role = nextcord.utils.get(Guild.roles, name=color)
        count = len(role.members)
        color_distribution.append(f"- {color}: {count}")
    embed.add_field(name='Color Click Distribution', value='\n'.join(color_distribution), inline=False)
    return embed