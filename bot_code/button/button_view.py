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

    def add_button(self):
        try:
            game_id = int(self.game_id) if self.game_id else None
            sessions_dict = game_sessions_dict()
            game_session = sessions_dict.get(game_id) if game_id else None
            timer_duration = game_session['timer_duration'] if game_session else 43200
            
            logger.debug(f"ButtonView - Game ID: {game_id}, Timer Duration: {timer_duration}")
            
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
