# Utils.py
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import traceback
import datetime
from nextcord import File, ButtonStyle
import logging
import json
import asyncio
import os

lock = asyncio.Lock()

os.chdir(os.path.dirname(os.path.abspath(__file__)))
log_file_name = f'..\\..\\logs\\theButton-{datetime.datetime.now().strftime("%Y-%m-%d")}.log'
logging.basicConfig(filename=log_file_name, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_config():
    with open('..\\..\\assets\\config.json', 'r') as f:
        config = json.load(f)
    return config

config = get_config()
    
COLOR_STATES = [
    (255, 89, 94),
    (255, 146, 76),
    (255, 202, 58),
    (138, 201, 38),
    (25, 130, 196),
    (106, 76, 147)
]

def get_color_state(timer_value):
    hours_remaining = int(timer_value) // 3600
    color_index = min(int(hours_remaining // 2), len(COLOR_STATES) - 1)
    return COLOR_STATES[color_index]

def get_color_name(timer_value):
    color = get_color_state(timer_value)
    if color == COLOR_STATES[0]:
        return "Red"
    elif color == COLOR_STATES[1]:
        return "Orange"
    elif color == COLOR_STATES[2]:
        return "Yellow"
    elif color == COLOR_STATES[3]:
        return "Green"
    elif color == COLOR_STATES[4]:
        return "Blue"
    elif color == COLOR_STATES[5]:
        return "Purple"
    return None

def get_button_style(color):
    style = ButtonStyle.gray
    if color == COLOR_STATES[0]:
        style = ButtonStyle.danger
    elif color == COLOR_STATES[1]:
        style = ButtonStyle.secondary
    elif color == COLOR_STATES[2]:
        style = ButtonStyle.secondary
    elif color == COLOR_STATES[3]:
        style = ButtonStyle.success
    elif color == COLOR_STATES[4]:
        style = ButtonStyle.primary
    elif color == COLOR_STATES[5]:
        style = ButtonStyle.primary
    return style

def get_color_emoji(timer_value):
    color = get_color_state(timer_value)
    if color == (255, 89, 94):
        return "🔴"
    elif color == (255, 146, 76):
        return "🟠"
    elif color == (255, 202, 58):
        return "🟡"
    elif color == (138, 201, 38):
        return "🟢"
    elif color == (25, 130, 196):
        return "🔵"
    elif color == (106, 76, 147):
        return "🟣"


def generate_timer_image(timer_value):
    try:
        color = get_color_state(timer_value)
        image_number = 6 - (COLOR_STATES.index(color))
        image_path = f"..\\..\\assets\\TheButtonTemplate{image_number:02d}.png"
        image = Image.open(image_path)
        
        # Draw the timer text on the image
        draw = ImageDraw.Draw(image)
        font_size = int(120 * 0.32)
        font = ImageFont.truetype('..\\..\\assets\\Mercy Christole.ttf', font_size)
        text = f"{format(int(timer_value//3600), '02d')}:{format(int(timer_value%3600//60), '02d')}:{format(int(timer_value%60), '02d')}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((image.width - text_width) // 2, (image.height - text_height) // 2 + 35)
        draw.text(position, text, font=font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        additional_text = "Time Left".upper()
        additional_font_size = int(100 * 0.32) 
        additional_font = ImageFont.truetype('..\\..\\assets\\Mercy Christole.ttf', additional_font_size)
        additional_text_bbox = draw.textbbox((0, 0), additional_text, font=additional_font)
        additional_text_width = additional_text_bbox[2] - additional_text_bbox[0]
        additional_text_height = additional_text_bbox[3] - additional_text_bbox[1]
        additional_position = ((image.width - additional_text_width) // 2, 70, ((image.height - additional_text_height) // 2) + 50)
        draw.text(additional_position, additional_text, font=additional_font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Save the image to an in-memory buffer
        buffer = BytesIO()
        image.save(buffer, 'PNG')
        buffer.seek(0)

        # Create a Discord File object from the buffer
        file = File(buffer, filename='timer.png')
        return file
    except Exception as e:
        tb = traceback.format_exc()
        print(f'Error generating timer image: {e}, {tb}')
        logger.error(f'Error generating timer image: {e}, {tb}')
        return None

def format_time(timer_value):
    timer_value = int(timer_value)
    time = str(datetime.timedelta(seconds=timer_value))
    return time