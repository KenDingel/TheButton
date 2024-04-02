# ButtonView class for the timer button
import asyncio
import nextcord
import traceback
import datetime
from datetime import timezone

# Local imports
from utils.utils import get_color_state, get_button_style
from utils.timer_button import TimerButton

# ButtonView class
# This class is used to create the button view for the timer button.
class ButtonView(nextcord.ui.View):
    def __init__(self, timer_value, bot):
        super().__init__(timeout=None)
        self.timer_value = timer_value
        self.bot = bot
        self.add_button()

    def add_button(self):
        button_label = "Click me!"
        color = get_color_state(self.timer_value)
        style = get_button_style(color)
        self.clear_items()
        button = TimerButton(style=style, label=button_label, timer_value=self.timer_value, bot=self.bot)
        self.add_item(button)