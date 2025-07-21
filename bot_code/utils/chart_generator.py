"""
Chart generation module for the Button Game.
Creates player-focused and game-focused visualizations.
"""
import io
import os
import logging
import traceback
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Circle
import matplotlib.gridspec as gridspec
import numpy as np
from typing import Dict, List, Tuple, Optional

# Set up logging
logger = logging.getLogger(__name__)

# Define colors for button states
COLOR_MAP = {
    'Purple': '#6A4C93',
    'Blue': '#3B83BD',
    'Green': '#4CAF50',
    'Yellow': '#FFC107',
    'Orange': '#FF9800',
    'Red': '#F44336',
    'Unknown': '#CCCCCC'
}

EMOJI_COLOR_MAP = {
    '🟣': 'Purple',
    '🔵': 'Blue',
    '🟢': 'Green',
    '🟡': 'Yellow',
    '🟠': 'Orange',
    '🔴': 'Red'
}



class ChartGenerator:
    """Class to handle generation of chart images for the button game."""
    
    def __init__(self):
        """Initialize the chart generator with styling."""
        try:
            # Set up matplotlib style
            plt.style.use('dark_background')
            self.fig_size = (12, 8)
            self.dpi = 100
            
            # Font configuration
            plt.rcParams.update({
                'font.size': 10,
                'axes.titlesize': 14,
                'axes.labelsize': 12,
                'xtick.labelsize': 10,
                'ytick.labelsize': 10,
                'legend.fontsize': 10,
                'figure.titlesize': 16
            })
            
        except Exception as e:
            logger.error(f"Error initializing ChartGenerator: {e}\n{traceback.format_exc()}")
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into HH:MM:SS format."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    
    def _emoji_to_color(self, emoji: str) -> str:
        """Convert emoji to color hex code."""
        color_name = EMOJI_COLOR_MAP.get(emoji, 'Unknown')
        return COLOR_MAP.get(color_name, '#CCCCCC')
    
    def _get_timer_color(self, timer_value: float, timer_duration: float) -> str:
        """Get color based on timer value and duration."""
        percentage = (timer_value / timer_duration) * 100
        
        if percentage >= 83.33:
            return COLOR_MAP['Purple']
        elif percentage >= 66.67:
            return COLOR_MAP['Blue']
        elif percentage >= 50.00:
            return COLOR_MAP['Green']
        elif percentage >= 33.33:
            return COLOR_MAP['Yellow']
        elif percentage >= 16.67:
            return COLOR_MAP['Orange']
        else:
            return COLOR_MAP['Red']
    
    def _get_timer_color_name(self, timer_value: float, timer_duration: float) -> str:
        """Get color name based on timer value and duration."""
        percentage = (timer_value / timer_duration) * 100
        
        if percentage >= 83.33:
            return 'Purple'
        elif percentage >= 66.67:
            return 'Blue'
        elif percentage >= 50.00:
            return 'Green'
        elif percentage >= 33.33:
            return 'Yellow'
        elif percentage >= 16.67:
            return 'Orange'
        else:
            return 'Red'
    
    def generate_player_charts(self, username: str, rank: int, total_players: int,
                              total_clicks: int, time_claimed: float, color_counts: Dict[str, int],
                              lowest_click_time: float, click_history: List[Tuple[float, datetime, str]],
                              timer_duration: float, server_stats: Optional[Dict] = None) -> io.BytesIO:
        """
        Generate player stats charts.
        
        Args:
            username: Player's username
            rank: Player's rank
            total_players: Total number of players
            total_clicks: Total number of clicks by player
            time_claimed: Total time claimed by player
            color_counts: Count of clicks by color
            lowest_click_time: Player's lowest click time
            click_history: Recent click history with times and colors
            timer_duration: Maximum timer duration
            server_stats: Optional server-wide stats for comparison
            
        Returns:
            BytesIO object containing the image
        """
        try:
            # Create figure with custom layout
            fig = plt.figure(figsize=self.fig_size, dpi=self.dpi)
            gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1.5])
            
            # Add super title
            fig.suptitle(f"{username}'s Button Stats", fontsize=20, y=0.98)
            
            # Add player summary
            summary_ax = fig.add_subplot(gs[0, 0])
            self._create_player_summary(summary_ax, username, rank, total_players, 
                                      total_clicks, time_claimed, lowest_click_time)
            
            # Add color distribution chart
            color_dist_ax = fig.add_subplot(gs[0, 1])
            self._create_color_distribution(color_dist_ax, color_counts)
            
            # Add click timeline
            timeline_ax = fig.add_subplot(gs[1, :])
            self._create_click_timeline(timeline_ax, click_history, timer_duration)
            
            # Adjust layout and save
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # Convert to BytesIO for Discord
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight')
            plt.close(fig)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logger.error(f"Error generating player charts: {e}\n{traceback.format_exc()}")
            # Create a simple error image
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(0.5, 0.5, "Error generating stats charts", 
                  ha='center', va='center', color='red', fontsize=14)
            ax.axis('off')
            
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png')
            plt.close(fig)
            buffer.seek(0)
            return buffer
    
    def _create_player_summary(self, ax, username, rank, total_players, 
                             total_clicks, time_claimed, lowest_click_time):
        """Create player summary panel."""
        # Hide axes
        ax.axis('off')
        
        # Add summary text
        text = [
            f"Rank: #{rank} of {total_players}",
            f"Total Clicks: {total_clicks}",
            f"Time Claimed: {self._format_time(time_claimed)}",
            f"Best Click: {self._format_time(lowest_click_time)}"
        ]
        
        # Calculate percentile
        percentile = 100 - (rank / total_players * 100)
        
        # Create a box for the stats
        props = dict(boxstyle='round', facecolor='#333333', alpha=0.6)
        
        # Join text with line breaks, add padding
        summary_text = '\n'.join(text)
        ax.text(0.5, 0.5, summary_text, transform=ax.transAxes,
              fontsize=12, verticalalignment='center', horizontalalignment='center',
              bbox=props)
        
        # Add percentile indicator
        ax.text(0.5, 0.1, f"Better than {percentile:.1f}% of players",
              transform=ax.transAxes, fontsize=10, alpha=0.8,
              verticalalignment='center', horizontalalignment='center')
    
    def _create_color_distribution(self, ax, color_counts):
        """Create color distribution bar chart."""
        colors = []
        counts = []
        
        # Sort colors in order: Purple, Blue, Green, Yellow, Orange, Red
        color_order = ['Purple', 'Blue', 'Green', 'Yellow', 'Orange', 'Red']
        
        for color in color_order:
            if color in color_counts and color_counts[color] > 0:
                colors.append(color)
                counts.append(color_counts[color])
        
        # If no data, show a message
        if not colors:
            ax.text(0.5, 0.5, "No color data available",
                  ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Create horizontal bar chart
        y_pos = np.arange(len(colors))
        ax.barh(y_pos, counts, align='center', color=[COLOR_MAP[c] for c in colors])
        ax.set_yticks(y_pos)
        ax.set_yticklabels(colors)
        
        # Add count labels
        for i, count in enumerate(counts):
            ax.text(count + max(counts) * 0.02, i, str(count), va='center')
        
        # Add title and labels
        ax.set_title('Color Distribution')
        ax.set_xlabel('Number of Clicks')
        
        # Add grid
        ax.grid(True, axis='x', alpha=0.3)
    
    def _create_click_timeline(self, ax, click_history, timer_duration):
        """Create click timeline scatter plot."""
        # If no data, show a message
        if not click_history:
            ax.text(0.5, 0.5, "No click history available",
                  ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Extract data
        click_times = [click_time for _, click_time, _ in click_history]
        timer_values = [timer_value for timer_value, _, _ in click_history]
        color_emojis = [emoji for _, _, emoji in click_history]
        
        # Map emojis to colors
        colors = [self._emoji_to_color(emoji) for emoji in color_emojis]
        
        # Create scatter plot
        scatter = ax.scatter(click_times, timer_values, c=colors, s=60, alpha=0.8, edgecolors='white')
        
        # Configure axes
        ax.set_title('Click Timeline')
        ax.set_xlabel('Date and Time')
        ax.set_ylabel('Timer Value (seconds)')
        
        # Configure date formatting
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Add color bands to visually show color thresholds
        self._add_color_bands(ax, timer_duration, click_times)
        
        # Add grid
        ax.grid(True, alpha=0.3)
        
        # Set y-axis limits with small padding
        y_min = max(0, min(timer_values) * 0.9)
        y_max = min(timer_duration, max(timer_values) * 1.1)
        ax.set_ylim(y_min, y_max)
        
        # Ensure x-axis covers all data with small padding
        date_range = max(click_times) - min(click_times)
        padding = date_range * 0.05
        ax.set_xlim(min(click_times) - padding, max(click_times) + padding)
    
    def _add_color_bands(self, ax, timer_duration, click_times):
        """Add color bands to the timeline to show color thresholds."""
        if not click_times:
            return
            
        # Define color thresholds as percentages of timer_duration
        thresholds = [
            (0, 16.67, COLOR_MAP['Red']),
            (16.67, 33.33, COLOR_MAP['Orange']),
            (33.33, 50.00, COLOR_MAP['Yellow']),
            (50.00, 66.67, COLOR_MAP['Green']),
            (66.67, 83.33, COLOR_MAP['Blue']),
            (83.33, 100, COLOR_MAP['Purple'])
        ]
        
        # Get x-axis limits
        x_min, x_max = min(click_times), max(click_times)
        date_range = x_max - x_min
        padding = date_range * 0.05
        x_min -= padding
        x_max += padding
        
        # Add colored bands
        for lower_pct, upper_pct, color in thresholds:
            lower_y = (lower_pct / 100) * timer_duration
            upper_y = (upper_pct / 100) * timer_duration
            ax.fill_between([x_min, x_max], lower_y, upper_y, color=color, alpha=0.1)
    
    def generate_game_charts(self, game_id: int, total_clicks: int, total_players: int,
                           time_elapsed: float, timer_duration: float, 
                           tier_stats: List[tuple], player_activity_data: List[tuple],
                           top_players_data: List[tuple]) -> io.BytesIO:
        """
        Generate game stats charts.
        
        Args:
            game_id: ID of the game
            total_clicks: Total number of clicks in the game
            total_players: Total number of players in the game
            time_elapsed: Total time elapsed in the game
            timer_duration: Maximum timer duration
            tier_stats: Statistics for each color tier
            player_activity_data: Player activity by hour of day
            top_players_data: Top players by time claimed
            
        Returns:
            BytesIO object containing the image
        """
        try:
            # Create figure with custom layout
            fig = plt.figure(figsize=self.fig_size, dpi=self.dpi)
            gs = gridspec.GridSpec(2, 2)
            
            # Add super title
            fig.suptitle(f"Game #{game_id} Stats", fontsize=20, y=0.98)
            
            # Add game summary
            summary_ax = fig.add_subplot(gs[0, 0])
            self._create_game_summary(summary_ax, game_id, total_clicks, total_players, time_elapsed)
            
            # Add tier stats chart
            tier_ax = fig.add_subplot(gs[0, 1])
            self._create_tier_stats_chart(tier_ax, tier_stats)
            
            # Add activity heatmap
            activity_ax = fig.add_subplot(gs[1, 0])
            self._create_activity_heatmap(activity_ax, player_activity_data)
            
            # Add top players chart
            players_ax = fig.add_subplot(gs[1, 1])
            self._create_top_players_chart(players_ax, top_players_data)
            
            # Adjust layout and save
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # Convert to BytesIO for Discord
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight')
            plt.close(fig)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logger.error(f"Error generating game charts: {e}\n{traceback.format_exc()}")
            # Create a simple error image
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.text(0.5, 0.5, "Error generating game stats charts", 
                  ha='center', va='center', color='red', fontsize=14)
            ax.axis('off')
            
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png')
            plt.close(fig)
            buffer.seek(0)
            return buffer
    
    def _create_game_summary(self, ax, game_id, total_clicks, total_players, time_elapsed):
        """Create game summary panel."""
        # Hide axes
        ax.axis('off')
        
        # Add summary text
        text = [
            f"Game ID: #{game_id}",
            f"Total Clicks: {total_clicks}",
            f"Total Players: {total_players}",
            f"Time Elapsed: {self._format_time(time_elapsed)}"
        ]
        
        # Calculate metrics
        avg_clicks_per_player = total_clicks / max(1, total_players)
        clicks_per_hour = total_clicks / max(1, time_elapsed / 3600)
        
        metrics = [
            f"Avg. Clicks per Player: {avg_clicks_per_player:.1f}",
            f"Clicks per Hour: {clicks_per_hour:.1f}"
        ]
        
        # Create a box for the stats
        props = dict(boxstyle='round', facecolor='#333333', alpha=0.6)
        
        # Join text with line breaks, add padding
        summary_text = '\n'.join(text + [''] + metrics)
        ax.text(0.5, 0.5, summary_text, transform=ax.transAxes,
              fontsize=12, verticalalignment='center', horizontalalignment='center',
              bbox=props)
    
    def _create_tier_stats_chart(self, ax, tier_stats):
        """Create color tier statistics chart."""
        # If no data, show a message
        if not tier_stats:
            ax.text(0.5, 0.5, "No tier stats available",
                  ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Extract data
        tiers = []
        clicks = []
        time_claimed = []
        colors = []
        
        for tier_info in tier_stats:
            tier_name, click_count, time_claimed_val, unique_clickers, avg_per_click, avg_per_user = tier_info
            tiers.append(tier_name)
            clicks.append(click_count)
            time_claimed.append(time_claimed_val)
            colors.append(COLOR_MAP.get(tier_name, '#CCCCCC'))
        
        # Create stacked bar chart
        x_pos = np.arange(len(tiers))
        width = 0.35
        
        clicks_bar = ax.bar(x_pos - width/2, clicks, width, label='Clicks')
        
        # Color the bars
        for i, bar in enumerate(clicks_bar):
            bar.set_color(colors[i])
            bar.set_alpha(0.7)
        
        # Add time claimed as a line on secondary y-axis
        ax2 = ax.twinx()
        time_line = ax2.plot(x_pos, time_claimed, 'o-', color='white', 
                           linewidth=2, markersize=8, label='Time Claimed')
        
        # Configure axes
        ax.set_title('Color Tier Statistics')
        ax.set_xlabel('Color Tier')
        ax.set_ylabel('Number of Clicks')
        ax2.set_ylabel('Time Claimed (seconds)')
        
        # Set tick labels
        ax.set_xticks(x_pos)
        ax.set_xticklabels(tiers)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Add grid
        ax.grid(True, axis='y', alpha=0.3)
        
        # Add legend
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines + lines2, labels + labels2, loc='upper right')
        
        # Add data labels
        for i, count in enumerate(clicks):
            ax.text(i - width/2, count, str(count), ha='center', va='bottom')
            
        for i, time_val in enumerate(time_claimed):
            ax2.text(i, time_val, self._format_time(time_val), ha='center', va='bottom')
    
    def _create_activity_heatmap(self, ax, player_activity_data):
        """Create player activity heatmap by hour of day."""
        # If no data, show a message
        if not player_activity_data:
            ax.text(0.5, 0.5, "No activity data available",
                  ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Extract data - assuming activity_data is a list of (hour, day_of_week, count) tuples
        # Reshape data into a 7x24 matrix (7 days, 24 hours)
        activity_matrix = np.zeros((7, 24))
        
        for hour, day, count in player_activity_data:
            activity_matrix[day, hour] = count
        
        # Create heatmap
        im = ax.imshow(activity_matrix, cmap='viridis')
        
        # Configure axes
        ax.set_title('Activity by Hour & Day')
        ax.set_xlabel('Hour of Day (UTC)')
        ax.set_ylabel('Day of Week')
        
        # Set tick labels
        ax.set_xticks(np.arange(0, 24, 3))
        ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)])
        
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        ax.set_yticks(np.arange(7))
        ax.set_yticklabels(days)
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Number of Clicks')
        
        # Add grid
        ax.grid(False)
    
    def _create_top_players_chart(self, ax, top_players_data):
        """Create top players chart by time claimed."""
        # If no data, show a message
        if not top_players_data:
            ax.text(0.5, 0.5, "No player data available",
                  ha='center', va='center', fontsize=12)
            ax.axis('off')
            return
        
        # Extract data
        players = []
        time_claimed = []
        colors = []
        
        for username, time_claimed_val, lowest_click, color_emoji in top_players_data:
            players.append(username)
            time_claimed.append(time_claimed_val)
            colors.append(self._emoji_to_color(color_emoji))
        
        # Create horizontal bar chart
        y_pos = np.arange(len(players))
        bars = ax.barh(y_pos, time_claimed, align='center', height=0.7)
        
        # Color the bars based on lowest click color
        for i, bar in enumerate(bars):
            bar.set_color(colors[i])
            bar.set_alpha(0.8)
        
        # Configure axes
        ax.set_title('Top Players by Time Claimed')
        ax.set_xlabel('Time Claimed (seconds)')
        ax.set_yticks(y_pos)
        ax.set_yticklabels(players)
        
        # Add time claimed labels
        for i, time_val in enumerate(time_claimed):
            ax.text(time_val + max(time_claimed) * 0.02, i, 
                  self._format_time(time_val), va='center')
        
        # Add grid
        ax.grid(True, axis='x', alpha=0.3)
        
        # Ensure all labels are visible
        plt.setp(ax.get_yticklabels(), fontsize=10)
        fig = plt.gcf()
        fig.canvas.draw()
        tl = ax.get_yticklabels()
        maxsize = max([t.get_window_extent().width for t in tl])
        ax.set_ylim(-0.5, len(players) - 0.5)  # Adjust limits to show all labels
