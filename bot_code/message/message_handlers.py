# message_handlers.py
import datetime
from datetime import timezone
import traceback
import nextcord
from database.database import *
from utils.utils import *
from text.full_text import *
from button.button_functions import setup_roles, create_button_message, paused_games

async def handle_message(message, bot, logger, menu_timer):
    global cursor, db, paused_games
    if message.author == bot.user and message.content.lower() != "sb": return
    if message.channel.id not in get_all_game_channels(): return
    
    logger.info(f"Message received in {message.guild.name}: {message.content}")
    try:
        if message.content.lower() == 'startbutton' or message.content.lower() == 'sb':
            logger.info(f"Starting button game in {message.guild.name}")
            if message.author.guild_permissions.administrator or message.author == bot.user:
                await message.channel.purge(limit=10, check=lambda m: m.author == bot.user)
                
                async for m in message.channel.history(limit=5):
                    if m.author == bot.user and (m.content.lower() == "sb" or m.content.lower() == "startbutton"):
                        try:
                            await m.delete()
                        except:
                            pass
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
                        
                    paused_games.remove(game_id)
                    await setup_roles(message.guild.id)
                    await create_button_message(game_id, bot)
                    update_local_game_sessions()
                
                if not menu_timer.update_timer_task.is_running():
                    logger.info('Starting update timer task...')
                    menu_timer.update_timer_task.start()
            else:
                await message.channel.send('You do not have permission to start the button game.')
                
            try:
                await message.delete()
            except:
                pass
        
        elif message.content.lower() == 'myrank' or message.content.lower() == 'rank':
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
                    logger.error(f'Error retrieving user rank: {e}, {tb}')
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
                            title='Your Heroic Journey'
                        )
                        embed.add_field(name='🎖️ Adventurer', value=user_check_name, inline=False)
                        embed.add_field(name='📜 Click History', value=emoji_sequence, inline=False)
                        embed.add_field(name='🎨 Color Summary', value=color_summary, inline=False)
                        embed.add_field(name='⏱️ Total Time Claimed*', value=format_time(total_claimed_time), inline=False)
                        embed.set_footer(text="*Total time claimed represents the amount of time you've prevented the clock from reaching zero.")
                    else:
                        user = await bot.fetch_user(user_check_id)
                        user_check_name = user.display_name if user.display_name else user.name
                        embed = nextcord.Embed(
                            title=f'Heroic Journey of {user_check_name}'
                        )
                        embed.add_field(name='🎖️ Adventurer', value=user_check_name, inline=False)
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
                    num_entries = int(message.content.split(" ")[1])
                except ValueError:
                    pass
            try:
                query = '''
                    SELECT 
                        u.user_name,
                        COUNT(*) AS total_clicks,
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
                    ORDER BY total_clicks DESC
                    LIMIT %s
                '''
                await lock.acquire()
                success = execute_query(query, (num_entries,))
                lock.release()
                most_clicks = success
                
                query = '''
                    SELECT u.user_name, bc.timer_value
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    ORDER BY bc.timer_value
                    LIMIT %s
                '''
                await lock.acquire()
                success = execute_query(query, (num_entries,))
                lock.release()
                lowest_individual_clicks = success

                query = '''
                    SELECT u.user_name, MIN(bc.timer_value) AS lowest_click_time
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    GROUP BY u.user_id
                    ORDER BY lowest_click_time
                    LIMIT %s
                '''
                await lock.acquire()
                success = execute_query(query, (num_entries,))
                lock.release()
                lowest_user_clicks = success

                query = '''
                    SELECT
                        u.user_name,
                        SUM(43200 - bc.timer_value) AS total_time_claimed
                    FROM button_clicks bc
                    JOIN users u ON bc.user_id = u.user_id
                    GROUP BY u.user_id
                    ORDER BY total_time_claimed DESC
                    LIMIT %s
                '''
                await lock.acquire()
                success = execute_query(query, (num_entries,))
                lock.release()
                most_time_claimed = success

                embed = nextcord.Embed(
                    title='🏆 The Leaderboard Legends of the Button 🏆')

                top_clicks_value = '\n'.join(
                    f'{user.replace(".", "")}: {clicks} clicks ({" ".join(emoji + "x" + str(seq.count(emoji)) for emoji in ["🟣", "🔵", "🟢", "🟡", "🟠", "🔴"] if emoji in seq)})'
                    for user, clicks, seq in most_clicks
                )
                embed.add_field(name='⚔️ Mightiest Clickers ⚔️', value='The adventurers who have clicked the button the most times.', inline=False)
                embed.add_field(name='Top Clickers', value=top_clicks_value if top_clicks_value else 'No data available', inline=False)

                lowest_individual_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_individual_clicks
                )
                embed.add_field(name='⚡ Swiftest Clicks ⚡', value='The adventurers who have clicked the button with the lowest time remaining.', inline=False)
                embed.add_field(name='Fastest Clicks', value=lowest_individual_clicks_value if lowest_individual_clicks_value else 'No data available', inline=False)

                lowest_user_clicks_value = '\n'.join(
                    f'{get_color_emoji(click_time)} {user.replace(".", "")}: {format_time(click_time)}'
                    for user, click_time in lowest_user_clicks
                )
                embed.add_field(name='🎯 Nimblest Warriors 🎯', value='The adventurers who have the lowest personal best click time.', inline=False)
                embed.add_field(name='Lowest Personal Best', value=lowest_user_clicks_value if lowest_user_clicks_value else 'No data available', inline=False)

                most_time_claimed_value = '\n'.join(
                    f'{user.replace(".", "")}: {format_time(time_claimed)}'
                    for user, time_claimed in most_time_claimed
                )
                embed.add_field(name='⏳ Temporal Titans ⏳', value='The adventurers who have claimed the most time by resetting the clock.', inline=False)
                embed.add_field(name='Most Time Claimed', value=most_time_claimed_value if most_time_claimed_value else 'No data available', inline=False)

                if lowest_individual_clicks:
                    color = get_color_state(lowest_individual_clicks[0][1])
                    embed.color = nextcord.Color.from_rgb(*color)
                else:
                    embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

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
                await lock.acquire()
                success = execute_query(query, ())
                lock.release()
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
                
                if all_users_value:
                    embed.add_field(name=f'🏅 Adventurers of the Button (Part {field_count}) 🏅', value=all_users_value, inline=False)
                
                if not all_users_data:
                    embed.add_field(name='🏅 Adventurers of the Button 🏅', value='No data available', inline=False)
                
                if all_users_data:
                    color = get_color_state(all_users_data[0][2])
                    embed.color = nextcord.Color.from_rgb(*color)
                else:
                    embed.color = nextcord.Color.from_rgb(106, 76, 147)  # Default color if no data available

                await message.channel.send(embed=embed)
            except Exception as e:
                tb = traceback.format_exc()
                print(f'Error retrieving end game data: {e}, {tb}')
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
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error processing message: {e}, {tb}')