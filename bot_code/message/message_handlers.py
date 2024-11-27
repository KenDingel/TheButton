# message_handlers.py
import datetime
from datetime import timezone
import traceback
import nextcord

# Local imports
from database.database import get_game_session_by_guild_id, create_game_session, get_game_session_by_id, get_all_game_channels, execute_query, game_sessions_dict, update_local_game_sessions, insert_first_click
from utils.utils import config, logger, lock, format_time, get_color_emoji, get_color_state
from text.full_text import LORE_TEXT
from button.button_functions import setup_roles, create_button_message, paused_games


# Handle message function
# This function is responsible for handling messages in the game channels.
# Command List: <command_name>: <command_in_discord> **<description>**
# - startbutton: sb **Starts the button game**
# - myrank: rank **Check your personal stats**
# - leaderboard: scores, scoreboard, top **Check the top 10 clickers**
# - check **Check if you have a click ready**
async def handle_message(message, bot, menu_timer):
    global paused_games, lock, logger
    if message.author == bot.user and message.content.lower() != "sb": return
    if message.channel.id not in [
        1236468062107209758, 1236468247856156722, # Moon's Server
        1305588554210087105, 1305588592147693649, 
        1305622604261883955, 1305683310525288448, 
        1308486315502997574, 1308488586215292988, # Goon Squad
        1310445586394382357, 1310445611652223047, # Lilith's Den
        1311011995868336209, 1311012042907586601
        ]: return #get_all_game_channels() and message.content.lower() != 'sb': return
    
    logger.info(f"Message received in {message.guild.name}: {message.content}")
    try:
        
        if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
            logger.info(f"Starting button game in {message.guild.name}")
            # Check if the user has admin permissions or is the bot
            if (message.author.guild_permissions.administrator or message.author.id == 692926265405079632) or message.author == bot.user:
                #await message.channel.purge(limit=10, check=lambda m: m.author == bot.user)
                
                async for m in message.channel.history(limit=5):
                    if m.author == bot.user and (m.content.lower() == "sb" or m.content.lower() == "startbutton"):
                        try: await m.delete()
                        except: pass
                        
                game_session = get_game_session_by_guild_id(message.guild.id)
                if game_session:
                    await create_button_message(game_session['game_id'], bot)
                    logger.info(f"Button game already started in {message.guild.name}")
                else:
                    logger.info(f"Starting button game in {message.guild.name}")
                    start_time = datetime.datetime.now(timezone.utc)
                    timer_duration = message.content.split(" ")[1] if len(message.content.split(" ")) > 2 else config['timer_duration']
                    cooldown_duration = message.content.split(" ")[2] if len(message.content.split(" ")) > 2 else config['cooldown_duration']
                    chat_channel_id = message.content.split(" ")[3] if len(message.content.split(" ")) > 3 else message.channel.id
                    
                    admin_role_id = 0
                    try:
                        admin_role = nextcord.utils.get(message.guild.roles, name='Button Master')
                        if not admin_role: admin_role = await message.guild.create_role(name='Button Master')
                        if not admin_role in message.author.roles: await message.author.add_roles(admin_role)
                        admin_role_id = admin_role.id
                    except Exception as e:
                        tb = traceback.format_exc()
                        logger.error(f'Error adding role: {e}, {tb}')
                        logger.info('Skipping role addition...')
                    
                    game_id = create_game_session(admin_role_id, message.guild.id, message.channel.id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                    
                    game_session = get_game_session_by_id(game_id)
                    game_sessions_as_dict = game_sessions_dict()
                    if game_sessions_as_dict:
                        game_sessions_as_dict[game_id] = game_session
                    else:
                        game_sessions_as_dict = {game_id: game_session}

                    update_local_game_sessions()
                    
                    if game_id in paused_games: 
                        try:
                            paused_games.remove(game_id)
                            logger.info(f'Game session {game_id} removed from paused games.')
                        except Exception as e:
                            tb = traceback.format_exc()
                            logger.error(f'Error removing game session from paused games: {e}, {tb}')
                            pass
                    
                    await setup_roles(message.guild.id, bot)
                    update_local_game_sessions()
                    await create_button_message(game_id, bot)
                
                if menu_timer and not menu_timer.update_timer_task.is_running():
                    logger.info('Starting update timer task...')
                    menu_timer.update_timer_task.start()
                elif not menu_timer:
                    logger.error('Menu timer not found.')
        
            else: await message.channel.send('You do not have permission to start the button game.')
                
            try: await message.delete()
            except: pass

        elif message.content.lower() == 'insert_first_click': #insert_first_click from database
            try:
                user_id = message.author.id
                game_session = get_game_session_by_guild_id(message.guild.id)
                username = message.author.display_name if message.author.display_name else message.author.name
                now = 43200
                result = insert_first_click(game_session['game_id'], user_id, username, now)
                if result:
                    logger.info(f'First click inserted for {username}')
                    await message.channel.send(f'First click inserted for {username}')
                else:
                    logger.error('Failed to insert first click.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error inserting first click: {e}, {tb}')
        
        elif message.content.lower() == 'myrank' or message.content.lower() == 'rank':
            await message.add_reaction('⏳')
            game_session = get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            is_other_user = False
            if len(message.content.split(" ")) > 1:
                user_check_id = int(message.content.split(" ")[1][3:-1])
                is_other_user = True
            else:
                user_check_id = message.author.id

            try:
                # Get user's clicks for current game session
                query = '''
                    SELECT 
                        bc.timer_value,
                        bc.click_time,
                        (
                            SELECT COUNT(DISTINCT u2.user_id)
                            FROM button_clicks bc2 
                            JOIN users u2 ON bc2.user_id = u2.user_id 
                            WHERE bc2.game_id = %s 
                            AND u2.total_clicks > (
                                SELECT COUNT(*) 
                                FROM button_clicks bc3 
                                WHERE bc3.user_id = %s 
                                AND bc3.game_id = %s
                            )
                        ) + 1 AS user_rank,
                        (
                            SELECT COUNT(DISTINCT user_id) 
                            FROM button_clicks 
                            WHERE game_id = %s
                        ) AS total_players
                    FROM button_clicks bc
                    WHERE bc.game_id = %s 
                    AND bc.user_id = %s
                    ORDER BY bc.click_time
                '''
                params = (game_session['game_id'], user_check_id, game_session['game_id'], 
                         game_session['game_id'], game_session['game_id'], user_check_id)
                success = execute_query(query, params)
                if not success: 
                    logger.error('Error retrieving user rank data')
                    await message.channel.send('An error occurred while retrieving rank data!')
                    await message.remove_reaction('⏳', bot.user)
                    await message.add_reaction('❌')
                    return

                clicks = success

                def Counter(emojis):
                    counts = {}
                    for emoji in emojis:
                        if emoji in counts:
                            counts[emoji] += 1
                        else:
                            counts[emoji] = 1
                    return counts

                if clicks:
                    color_emojis = [get_color_emoji(timer_value, game_session['timer_duration']) for timer_value, _, _, _ in clicks]
                    color_counts = Counter(color_emojis)
                    total_claimed_time = sum(config['timer_duration'] - timer_value for timer_value, _, _, _ in clicks)
                    emoji_sequence = ' '.join(color_emojis)
                    color_summary = ', '.join(f'{emoji} x{count}' for emoji, count in color_counts.items())
                    rank = clicks[0][2]  # Get rank from first row
                    total_players = clicks[0][3]  # Get total players from first row

                    if not is_other_user:
                        user_check_name = message.author.display_name if message.author.display_name else message.author.name
                        embed = nextcord.Embed(title='Your Heroic Journey')
                        embed.add_field(name='🎖️ Adventurer', value=user_check_name, inline=False)
                        embed.add_field(name='👑 Current Rank', value=f'#{rank} out of {total_players} adventurers', inline=False)
                        embed.add_field(name='📜 Click History', value=emoji_sequence, inline=False)
                        embed.add_field(name='🎨 Color Summary', value=color_summary, inline=False)
                        embed.add_field(name='⏱️ Total Time Claimed*', value=format_time(total_claimed_time), inline=False)
                        embed.set_footer(text="*Total time claimed represents the amount of time you've prevented the clock from reaching zero.")
                    else:
                        user = await bot.fetch_user(user_check_id)
                        user_check_name = user.display_name if user.display_name else user.name
                        embed = nextcord.Embed(title=f'Heroic Journey of {user_check_name}')
                        embed.add_field(name='🎖️ Adventurer', value=user_check_name, inline=False)
                        embed.add_field(name='👑 Current Rank', value=f'#{rank} out of {total_players} adventurers', inline=False)
                        embed.add_field(name='📜 Click History', value=emoji_sequence, inline=False)
                        embed.add_field(name='🎨 Color Summary', value=color_summary, inline=False)
                        embed.add_field(name='⏱️ Total Time Claimed*', value=format_time(total_claimed_time), inline=False)
                        embed.set_footer(text="*Total time claimed represents the amount of time they've prevented the clock from reaching zero.")
                    await message.channel.send(embed=embed)
                else:
                    if not is_other_user: 
                        await message.channel.send('Alas, noble warrior, your journey has yet to begin. Step forth and make your mark upon the button!')
                    else:
                        await message.channel.send('Alas, noble warrior, their journey has yet to begin. Step forth and make your mark upon the button!')

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving user rank: {e}, {tb}')
                if not is_other_user:
                    await message.channel.send('An error occurred while retrieving your rank. The button spirits are displeased!')
                else:
                    await message.channel.send('An error occurred while retrieving the user rank. The button spirits are displeased!')
            finally:
                try:
                    await message.remove_reaction('⏳', bot.user)
                except:
                    pass

        elif message.content.lower() in ['leaderboard', 'scores', 'scoreboard', 'top']:
            await message.add_reaction('⏳')
            game_session = get_game_session_by_guild_id(message.guild.id)
            if not game_session:
                await message.channel.send('No active game session found in this server!')
                return

            num_entries = 5
            if len(message.content.split()) > 1:
                try:
                    num_entries = int(message.content.split(" ")[1])
                except ValueError:
                    pass

            try:
                # Most clicks in current game session
                query = '''
                        SELECT 
                            u.user_name,
                            COUNT(*) AS total_clicks,
                            GROUP_CONCAT(
                                CASE
                                    WHEN (bc.timer_value / %s) * 100 >= 83.33 THEN '🟣'
                                    WHEN (bc.timer_value / %s) * 100 >= 66.67 THEN '🔵'
                                    WHEN (bc.timer_value / %s) * 100 >= 50 THEN '🟢'
                                    WHEN (bc.timer_value / %s) * 100 >= 33.33 THEN '🟡'
                                    WHEN (bc.timer_value / %s) * 100 >= 16.67 THEN '🟠'
                                    ELSE '🔴'
                                END
                                ORDER BY bc.timer_value
                                SEPARATOR ''
                            ) AS color_sequence
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        WHERE bc.game_id = %s
                        GROUP BY u.user_id
                        ORDER BY total_clicks DESC
                        LIMIT %s
                        '''
                params = (game_session['timer_duration'], game_session['timer_duration'], 
                        game_session['timer_duration'], game_session['timer_duration'],
                        game_session['timer_duration'], game_session['game_id'], num_entries)
                success = execute_query(query, params)
                most_clicks = success

                # Lowest individual clicks in current game session
                query = '''
                    SELECT u.user_name, bc.timer_value
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    ORDER BY bc.timer_value
                    LIMIT %s
                '''
                success = execute_query(query, (game_session['game_id'], num_entries))
                lowest_individual_clicks = success

                # Lowest user clicks in current game session
                query = '''
                    SELECT u.user_name, MIN(bc.timer_value) AS lowest_click_time
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY lowest_click_time
                    LIMIT %s
                '''
                success = execute_query(query, (game_session['game_id'], num_entries))
                lowest_user_clicks = success

                # Most time claimed in current game session
                query = '''
                    SELECT
                        u.user_name,
                        SUM(43200 - bc.timer_value) AS total_time_claimed
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    WHERE bc.game_id = %s
                    GROUP BY u.user_id
                    ORDER BY total_time_claimed DESC
                    LIMIT %s
                '''
                success = execute_query(query, (game_session['game_id'], num_entries))
                most_time_claimed = success

                embed = nextcord.Embed(
                    title='🏆 The Leaderboard Legends of the Button 🏆')

                top_clicks_value = '\n'.join(
                    f'{user.replace(".", "")}: {clicks} clicks ({" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)})'
                    for user, clicks, seq in most_clicks
                )
                embed.add_field(name='⚔️ Mightiest Clickers ⚔️', 
                              value='The adventurers who have clicked the button the most times in this game.', 
                              inline=False)
                embed.add_field(name='Top Clickers', 
                              value=top_clicks_value if top_clicks_value else 'No data available', 
                              inline=False)

                lowest_individual_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_individual_clicks
                )
                embed.add_field(name='⚡ Swiftest Clicks ⚡', 
                              value='The adventurers who have clicked the button with the lowest time remaining in this game.', 
                              inline=False)
                embed.add_field(name='Fastest Clicks', 
                              value=lowest_individual_clicks_value if lowest_individual_clicks_value else 'No data available', 
                              inline=False)

                lowest_user_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_user_clicks
                )
                embed.add_field(name='🎯 Nimblest Warriors 🎯', 
                              value='The adventurers who have the lowest personal best click time in this game.', 
                              inline=False)
                embed.add_field(name='Lowest Personal Best', 
                              value=lowest_user_clicks_value if lowest_user_clicks_value else 'No data available', 
                              inline=False)

                most_time_claimed_value = '\n'.join(
                    f'{user.replace(".", "")}: {format_time(time_claimed)}'
                    for user, time_claimed in most_time_claimed
                )
                embed.add_field(name='⏳ Temporal Titans ⏳', 
                              value='The adventurers who have claimed the most time by resetting the clock in this game.', 
                              inline=False)
                embed.add_field(name='Most Time Claimed', 
                              value=most_time_claimed_value if most_time_claimed_value else 'No data available', 
                              inline=False)

                if lowest_individual_clicks:
                    color = get_color_state(lowest_individual_clicks[0][1], game_session['timer_duration'])
                    embed.color = nextcord.Color.from_rgb(*color)
                else:
                    embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                embed.description = f"Gather round, brave adventurers, and marvel at the legends whose names shall be etched in the button's eternal memory for Game #{game_session['game_id']}!"

                await message.channel.send(embed=embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving leaderboard: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the leaderboard. The button archives are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower().startswith('clicklist'):
            await message.add_reaction('⌛')
            try:
                # Parse command arguments
                args = message.content.lower().split()
                limit = 25  # Default limit
                is_global = False
                
                # Process arguments
                for arg in args[1:]:
                    if arg.isdigit():
                        limit = min(int(arg), 100)  # Cap at 100 entries
                    elif arg == 'global':
                        is_global = True

                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session and not is_global:
                    await message.channel.send('No active game session found in this server!')
                    return

                # Construct the SQL query based on whether it's global or server-specific
                if is_global:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (limit,)
                else:
                    query = '''
                        SELECT 
                            bc.timer_value,
                            bc.click_time,
                            u.user_name,
                            gs.guild_id,
                            gs.id as game_session_id
                        FROM button_clicks bc
                        JOIN users u ON bc.user_id = u.user_id
                        JOIN game_sessions gs ON bc.game_id = gs.id
                        WHERE bc.game_id = %s
                        ORDER BY bc.timer_value ASC
                        LIMIT %s
                    '''
                    params = (game_session['game_id'], limit)

                results = execute_query(query, params)
                
                if not results:
                    await message.channel.send('No clicks found!')
                    await message.remove_reaction('⌛', bot.user)
                    return

                # Create embed
                title = f"🎯 The Button - {'Global ' if is_global else ''}Lowest {limit} Clicks"
                embed = nextcord.Embed(title=title)
                
                # Process results in chunks to respect Discord's field length limits
                current_field = ""
                field_count = 1
                
                for timer_value, click_time, user_name, guild_id, game_session_id in results:
                    # Get color emoji based on timer value
                    color_emoji = get_color_emoji(timer_value)
                    
                    # Format the click entry
                    entry = f"{color_emoji} **{user_name}** - {format_time(timer_value)} - "
                    entry += f"<t:{int(click_time.timestamp())}:R>\n"
                    
                    if is_global:
                        guild = bot.get_guild(guild_id)
                        guild_name = guild.name if guild else f"Unknown Server ({guild_id})"
                        entry += f"Server: {guild_name}\n"
                    
                    entry += "\n"  # Add spacing between entries
                    
                    # Check if adding this entry would exceed Discord's field limit
                    if len(current_field) + len(entry) > 1024:
                        embed.add_field(
                            name=f"Clicks (Part {field_count})", 
                            value=current_field, 
                            inline=False
                        )
                        current_field = entry
                        field_count += 1
                    else:
                        current_field += entry

                # Add the last field if there's any content
                if current_field:
                    embed.add_field(
                        name=f"Clicks {f'(Part {field_count})' if field_count > 1 else ''}", 
                        value=current_field, 
                        inline=False
                    )

                await message.channel.send(embed=embed)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving click list: {e}\n{tb}')
                await message.channel.send('An error occurred while retrieving the click list!')
            finally:
                await message.remove_reaction('⌛', bot.user)

        elif message.content.lower() == 'help':
            embed = nextcord.Embed(title='Help', description='Available Commands')
            embed.add_field(name='myrank', value='Check your personal stats', inline=False)
            embed.add_field(name='leaderboard', value='Check the top 10 clickers', inline=False)
            embed.add_field(name='check', value='Check if you have a click ready', inline=False)
            embed.add_field(name='clicklist [number] [global]', 
                          value='View the lowest click times. Add number (max 100) to see more entries, add global to see all servers.', 
                          inline=False)
            embed.set_footer(text='May your clicks be swift and true, adventurer!')
            color = (106, 76, 147)
            embed.color = nextcord.Color.from_rgb(*color)
            await message.channel.send(embed=embed)

        elif message.content.lower() == 'check':
            await message.add_reaction('⏳')
            user_check_id = message.author.id
            try:
                # Get the game session to access the cooldown duration
                game_session = get_game_session_by_guild_id(message.guild.id)
                if not game_session:
                    await message.channel.send('No active game session found in this server!')
                    await message.remove_reaction('‚è≥', bot.user)
                    return

                cooldown_duration = game_session['cooldown_duration']
                
                query = '''
                    SELECT COUNT(*) AS click_count 
                    FROM button_clicks 
                    WHERE user_id = %s 
                    AND click_time >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s HOUR)
                '''
                params = (user_check_id, cooldown_duration)
                success = execute_query(query, params)
                if not success:
                    logger.error('Failed to retrieve data.')
                    await message.add_reaction('‚ùå')
                    return
                
                result = success[0]
                click_count = result[0]
                if click_count == 0: response = "✅ Ah, my brave adventurer! Your spirit is ready, and the button awaits your valiant click. Go forth and claim your glory!"
                else: response = "❌ Alas, noble warrior, you must rest and gather your strength. The button shall beckon you again when the time is right."

                embed = nextcord.Embed(description=response)
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error checking user cooldown: {e}, {tb}')
                await message.channel.send('Alas noble warrior, an error occurred while checking your cooldown. The button spirits are in disarray!')
            finally:
                await message.remove_reaction('⏳', bot.user)

        elif message.content.lower() == 'ended':
            try:
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
                        MIN(bc.timer_value) AS lowest_click_time,
                        GROUP_CONCAT(
                            CASE
                                WHEN bc.timer_value >= 36000 THEN '🟣'
                                WHEN bc.timer_value >= 28800 THEN '🔵'
                                WHEN bc.timer_value >= 21600 THEN '🟢'
                                WHEN bc.timer_value >= 14400 THEN '🟡'
                                WHEN bc.timer_value >= 7200 THEN '🟠'
                                ELSE '🔴'
                            END
                            ORDER BY bc.timer_value
                            SEPARATOR ''
                        ) AS color_sequence
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    GROUP BY u.user_id
                    ORDER BY lowest_click_time
                '''
                success = execute_query(query, ())
                all_users_data = success
                
                embed = nextcord.Embed(
                    title='🎉 The Button Game Has Ended! 🎉',
                    description='Here are the final results of all the brave adventurers who participated in this epic journey!'
                )
                
                max_field_length = 1024
                field_count = 1
                all_users_value = ""
                
                for user, clicks, lowest_time, seq in all_users_data:
                    user_data = f'{user.replace(".", "")}: {clicks} clicks, Lowest: {format_time(lowest_time)} {" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)}\n'
                    
                    if len(all_users_value) + len(user_data) > max_field_length:
                        embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                        all_users_value = ""
                        field_count += 1
                    
                    all_users_value += user_data
                
                if all_users_value: embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                
                if not all_users_data: embed.add_field(name='🏅 Adventurers of the Button 🏅', value='No data available', inline=False)
                
                if all_users_data: color = get_color_state(all_users_data[0][2]); embed.color = nextcord.Color.from_rgb(*color)
                else: embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving end game data: {e}, {tb}')
                await message.channel.send('An error occurred while retrieving the end game data. The button spirits are in turmoil!')

        elif message.content.lower() == 'lore':
            try:
                embed = nextcord.Embed(title="📜 __The Lore of The Button__ 📜", description=LORE_TEXT)
                embed.set_footer(text="⚡ *May your clicks be swift and true, adventurer!* ⚡")
                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error retrieving lore: {e}, {tb}')
                await message.channel.send('❌ **An error occurred while retrieving the lore.** *The ancient archives seem to be temporarily sealed!* ❌')

        elif message.content.lower() == 'add_new_game':
            try:
                query = 'SELECT * FROM game_sessions'
                success = execute_query(query)
                game_sessions = success
                if game_sessions:
                    for game_session in game_sessions:
                        game_id = game_session[0]
                        game_channel_id = game_session[1]
                        chat_channel_id = game_session[2]
                        start_time = game_session[3]
                        timer_duration = game_session[4]
                        cooldown_duration = game_session[5]
                        admin_role_id = game_session[6]
                        guild_id = game_session[7]
                        paused_games.append(game_id)
                        create_game_session(admin_role_id, guild_id, game_channel_id, chat_channel_id, start_time, timer_duration, cooldown_duration)
                        logger.info(f'Game session {game_id} added to paused games.')
                    await message.channel.send('Game sessions added to paused games.')
                else:
                    await message.channel.send('No game sessions found.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error adding game sessions: {e}, {tb}')
                await message.channel.send('An error occurred while adding game sessions.')
    
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error processing message: {e}, {tb}')

async def start_boot_game(bot, button_guild_id, message_button_channel, menu_timer):
    global paused_games, lock, logger
    game_session = get_game_session_by_guild_id(button_guild_id)
    guild = bot.get_guild(button_guild_id)
    if game_session:
        await create_button_message(game_session['game_id'], bot)
        logger.info(f"Button game already started in {button_guild_id}")
    else:
        logger.info(f"Starting button game in {button_guild_id}")
        start_time = datetime.datetime.now(timezone.utc)
        timer_duration = config['timer_duration']
        cooldown_duration = config['cooldown_duration']
        chat_channel_id = message_button_channel
        
        admin_role_id = 0
        try:
            admin_role = nextcord.utils.get(guild.roles, name='Button Master')
            if not admin_role: admin_role = await guild.create_role(name='Button Master')
            admin_role_id = admin_role.id
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f'Error adding role: {e}, {tb}')
            logger.info('Skipping role addition...')
            pass
            
        game_id = create_game_session(admin_role_id, guild.id, message_button_channel, chat_channel_id, start_time, timer_duration, cooldown_duration)
        
        game_session = get_game_session_by_id(game_id)
        game_sessions_as_dict = game_sessions_dict()
        if game_sessions_as_dict:
            game_sessions_as_dict[game_id] = game_session
        else:
            game_sessions_as_dict = {game_id: game_session}

        update_local_game_sessions()
        
        if game_id in paused_games: 
            try:
                paused_games.remove(game_id)
                logger.info(f'Game session {game_id} removed from paused games.')
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f'Error removing game session from paused games: {e}, {tb}')
                pass
        
        await setup_roles(guild.id, bot)
        update_local_game_sessions()
        await create_button_message(game_id, bot)
        
    if menu_timer and not menu_timer.update_timer_task.is_running():
        logger.info('Starting update timer task...')
        menu_timer.update_timer_task.start()