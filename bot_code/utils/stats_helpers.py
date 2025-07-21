from typing import Dict, List, Tuple
import datetime

def get_color_distribution(clicks: List[Tuple[int, int]], timer_duration: int) -> Dict[str, int]:
    """
    Calculate distribution of colors for all clicks
    
    Args:
        clicks: List of (timer_value, timestamp) tuples
        timer_duration: Total duration of timer
        
    Returns:
        Dict mapping color emoji to count
    """
    colors = {
        '🟣': 0, '🔵': 0, '🟢': 0, 
        '🟡': 0, '🟠': 0, '🔴': 0
    }
    
    for timer_value, _ in clicks:
        percentage = (timer_value / timer_duration) * 100
        if percentage >= 83.33:
            colors['🟣'] += 1
        elif percentage >= 66.67:
            colors['🔵'] += 1
        elif percentage >= 50:
            colors['🟢'] += 1
        elif percentage >= 33.33:
            colors['🟡'] += 1
        elif percentage >= 16.67:
            colors['🟠'] += 1
        else:
            colors['🔴'] += 1
            
    return colors

def get_hourly_activity(clicks: List[Tuple[int, int]]) -> Dict[int, int]:
    """
    Calculate click distribution by hour
    
    Args:
        clicks: List of (timer_value, timestamp) tuples
        
    Returns:
        Dict mapping hour (0-23) to click count
    """
    hours = {i: 0 for i in range(24)}
    
    for _, timestamp in clicks:
        hour = datetime.datetime.fromtimestamp(timestamp).hour
        hours[hour] += 1
        
    return hours

def get_mmr_over_time(clicks: List[Tuple[int, int, int, str]], timer_duration: int) -> List[Dict]:
    """
    Calculate cumulative MMR progression
    
    Args:
        clicks: List of (timer_value, timestamp, user_id, username) tuples
        timer_duration: Total duration of timer
        
    Returns:
        List of dicts with timestamp and MMR values per user
    """
    user_mmr = {}
    progression = []
    
    for timer_value, timestamp, user_id, username in sorted(clicks, key=lambda x: x[1]):
        # Calculate MMR for this click using same formula as leaderboard
        percentage = (timer_value / timer_duration) * 100
        bracket = min(5, int(percentage / 16.66667))
        bracket_position = (percentage % 16.66667) / 16.66667
        
        base_points = 2 ** (5 - bracket)
        
        if bracket <= 1:
            position_multiplier = 1 - bracket_position
        else:
            position_multiplier = 1 - abs(0.5 - bracket_position)
            
        mmr = base_points * (1 + position_multiplier) * (timer_duration / 43200)
        
        if user_id not in user_mmr:
            user_mmr[user_id] = {'mmr': 0, 'username': username}
            
        user_mmr[user_id]['mmr'] += mmr
        
        progression.append({
            'timestamp': timestamp,
            'username': username,
            'mmr': user_mmr[user_id]['mmr']
        })
        
    return progression

def get_duration_emoji(days: float) -> str:
    """Get appropriate emoji for game duration."""
    if days >= 100:
        return "💎"  # Diamond for 100+ days
    elif days >= 50:
        return "🌟"  # Star for 50+ days
    elif days >= 30:
        return "🌙"  # Moon for 30+ days
    elif days >= 7:
        return "⭐"  # Star for 7+ days
    return "⌛"     # Hourglass for < 7 days

def format_game_duration(seconds: int) -> tuple[str, float]:
    """
    Format duration in seconds to days, hours, minutes format.
    Returns tuple of (formatted_string, days_float)
    """
    days = seconds // (24 * 3600)
    remaining = seconds % (24 * 3600)
    hours = remaining // 3600
    remaining %= 3600
    minutes = remaining // 60
    
    days_float = seconds / (24 * 3600)
    return f"{days}d {hours}h {minutes}m", days_float

def get_nearby_ranks(game_stats: list, current_game_id: int, total_shown: int = 5) -> list:
    """
    Get games ranked near the specified game.
    Args:
        game_stats: List of game statistics from database
        current_game_id: ID of the game to center around
        total_shown: Total number of games to show (default: 5)
    Returns:
        List of nearby ranked games
    """
    # Find current game's position
    current_pos = next((i for i, g in enumerate(game_stats) if g['game_id'] == current_game_id), None)
    if current_pos is None:
        return []
    
    # Calculate how many games to show before and after
    games_before = (total_shown - 1) // 2
    games_after = total_shown - games_before - 1
    
    # Adjust for edge cases
    if current_pos < games_before:
        # Near start, show more after
        games_before = current_pos
        games_after = total_shown - games_before - 1
    elif current_pos >= len(game_stats) - games_after:
        # Near end, show more before
        games_after = len(game_stats) - current_pos - 1
        games_before = total_shown - games_after - 1
    
    start_idx = max(0, current_pos - games_before)
    end_idx = min(len(game_stats), current_pos + games_after + 1)
    
    return game_stats[start_idx:end_idx]

def calculate_time_to_next_rank(current_duration: int, next_duration: int) -> str:
    """
    Calculate and format time needed to reach next rank.
    Args:
        current_duration: Current duration in seconds
        next_duration: Next rank's duration in seconds
    Returns:
        Formatted string showing time difference
    """
    diff = next_duration - current_duration
    days = diff // (24 * 3600)
    remaining = diff % (24 * 3600)
    hours = remaining // 3600
    remaining %= 3600
    minutes = remaining // 60
    
    return f"{days}d {hours}h {minutes}m"