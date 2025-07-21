# ButtonView class for the timer button
import nextcord
import traceback
import datetime
from datetime import timezone

# Local imports
from utils.utils import get_color_state, get_button_style, logger
from utils.timer_button import TimerButton
from database.database import game_sessions_dict

class ButtonView(nextcord.ui.View):
    def __init__(self, timer_value, bot, game_id=None):
        super().__init__(timeout=None)  # Correct timeout placement
        self.timer_value = timer_value
        self.bot = bot
        self.game_id = game_id
        self.add_button()

    async def get_game_session(self):
        """Helper method to get game session asynchronously"""
        try:
            game_id = int(self.game_id) if self.game_id else None
            if not game_id:
                return None
            sessions_dict = await game_sessions_dict()
            return sessions_dict.get(str(game_id))
        except Exception as e:
            logger.error(f"Error getting game session: {e}")
            return None

    def add_button(self):
        try:
            # Set default timer duration
            timer_duration = 43200  # Default 12 hours

            button_label = "Click me!"
            color = get_color_state(self.timer_value, timer_duration)
            style = get_button_style(color)
            
            self.clear_items()
            # Match parameters with TimerButton's __init__ signature
            button = TimerButton(
                bot=self.bot,
                style=style,
                label=button_label,
                timer_value=self.timer_value,
                game_id=self.game_id
            )
            self.add_item(button)
        except Exception as e:
            logger.error(f"Error in ButtonView.add_button: {e}")
            logger.error(traceback.format_exc())
            # Fallback with correct parameter order
            button = TimerButton(
                bot=self.bot,
                style=nextcord.ButtonStyle.primary,
                label="Click me!",
                timer_value=self.timer_value,
                game_id=self.game_id
            )
            self.add_item(button)