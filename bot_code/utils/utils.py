# Utils.py
import traceback
import datetime
import logging
import math
import json
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from nextcord import File, ButtonStyle
from threading import Lock
import asyncio
import sys

print("Starting utils file...")

# Get the base directory (parent of bot_code)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), '..'))
print(f"Base directory: {BASE_DIR}")

# Global lock to be imported by other modules
lock = asyncio.Lock()

# Set up logging before anything else
log_dir = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
        print(f"Created logs directory at {log_dir}")
    except Exception as e:
        print(f"Failed to create logs directory: {e}")
        sys.exit(1)

log_file_name = os.path.join(log_dir, f'theButton-{datetime.datetime.now().strftime("%Y-%m-%d")}.log')
try:
    logging.basicConfig(
        filename=log_file_name,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    # Also log to console for debugging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Logging to {log_file_name}")
except Exception as e:
    print(f"Failed to initialize logging: {e}")
    print(traceback.format_exc())
    sys.exit(1)

def get_config():
    """
    Load configuration from config.json file.
    Returns:
        dict: Configuration dictionary
    Raises:
        SystemExit: If config file cannot be found or read
    """
    config_path = os.path.join(BASE_DIR, 'assets', 'config.json')
    try:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logger.critical(f"Failed to load config: {e}")
        logger.critical(traceback.format_exc())
        print(f"Critical error loading config: {e}")
        sys.exit(1)

# Load the config file and set the paused games list as global variables 
try:
    config = get_config()
    logger.info("Config loaded successfully")
except Exception as e:
    logger.critical(f"Failed to initialize config: {e}")
    sys.exit(1)

paused_games = []

# Rest of your constants remain the same
GUILD_EMOJIS = [
    "🎮", "🎲", "🎯", "🎪", "🎨", "🎭", "🎪", "🌟", "🌙", "⭐",
    "🦁", "🐉", "🐲", "🦊", "🐺", "🦄", "🦅", "🦋", "🐝", "🦚",
    "⚔️", "🛡️", "🗡️", "🏹", "🪄", "🎭", "👑", "💫", "✨", "🌈"
]

COLOR_STATES = [
    (194, 65, 65),    # Red
    (219, 124, 48),   # Orange
    (203, 166, 53),   # Yellow
    (80, 155, 105),   # Green
    (64, 105, 192),   # Blue
    (106, 76, 147)    # Purple
]

def get_color_state(timer_value, timer_duration=43200):
    """
    Get the color state based on the remaining time, with precise decimal handling.
    """
    timer_value = max(0, min(float(timer_value), float(timer_duration)))
    timer_duration = max(1, float(timer_duration))
    
    # Use ROUND to match SQL precision
    percentage = round((timer_value / timer_duration) * 100, 2)
    
    logger.debug(f"Color calculation: timer_value={timer_value}, duration={timer_duration}, percentage={percentage}")
    
    if percentage >= 83.33:
        return COLOR_STATES[5]  # Purple
    elif percentage >= 66.67:
        return COLOR_STATES[4]  # Blue
    elif percentage >= 50.00:
        return COLOR_STATES[3]  # Green
    elif percentage >= 33.33:
        return COLOR_STATES[2]  # Yellow
    elif percentage >= 16.67:
        return COLOR_STATES[1]  # Orange
    else:
        return COLOR_STATES[0]  # Red

def get_color_emoji(timer_value, timer_duration=43200):
    """
    Get the color emoji based on the remaining time, with precise decimal handling.
    """
    timer_value = max(0, min(float(timer_value), float(timer_duration)))
    timer_duration = max(1, float(timer_duration))
    
    # Use ROUND to match SQL precision
    percentage = round((timer_value / timer_duration) * 100, 2)
    
    if percentage >= 83.33:
        return '🟣'  # Purple
    elif percentage >= 66.67:
        return '🔵'  # Blue
    elif percentage >= 50.00:
        return '🟢'  # Green
    elif percentage >= 33.33:
        return '🟡'  # Yellow
    elif percentage >= 16.67:
        return '🟠'  # Orange
    else:
        return '🔴'  # Red

def get_color_name(timer_value, timer_duration=43200):
    """
    Get the color name based on the remaining time, scaled to the timer duration.
    """
    timer_value = max(0, min(timer_value, timer_duration))
    timer_duration = max(1, timer_duration)
    
    percentage = (timer_value / timer_duration) * 100
    
    if percentage >= 83.33:
        return 'Purple'
    elif percentage >= 66.67:
        return 'Blue'
    elif percentage >= 50:
        return 'Green'
    elif percentage >= 33.33:
        return 'Yellow'
    elif percentage >= 16.67:
        return 'Orange'
    else:
        return 'Red'

def get_button_style(color):
    style = ButtonStyle.gray
    if color == COLOR_STATES[0]: style = ButtonStyle.danger
    elif color == COLOR_STATES[1]: style = ButtonStyle.secondary
    elif color == COLOR_STATES[2]: style = ButtonStyle.secondary
    elif color == COLOR_STATES[3]: style = ButtonStyle.success
    elif color == COLOR_STATES[4]: style = ButtonStyle.primary
    elif color == COLOR_STATES[5]: style = ButtonStyle.primary
    return style

def format_time(timer_value):
    timer_value = int(timer_value)
    time = str(datetime.timedelta(seconds=timer_value))
    return time

# Generate an image of the timer with text, color, and time left.
# Utilizes templates for each color state.
# Uses Pillow for image manipulation.
def legacy_generate_timer_image(timer_value, timer_duration=43200):
    try:
        # Prepare the image data and template
        color = get_color_state(timer_value, timer_duration)
        image_number = 6 - (COLOR_STATES.index(color))
        image_path = os.path.join(BASE_DIR, 'assets', f'TheButtonTemplate{image_number:02d}.png')
        font_path = os.path.join(BASE_DIR, 'assets', 'Mercy Christole.ttf')
        
        if not os.path.exists(image_path):
            logger.error(f"Template image not found: {image_path}")
            return None
            
        if not os.path.exists(font_path):
            logger.error(f"Font file not found: {font_path}")
            return None
            
        image = Image.open(image_path)
        
        # Draw the timer text on the image
        draw = ImageDraw.Draw(image)
        font_size = int(120 * 0.32)
        current_path = os.path.dirname(os.path.abspath(__file__))
        font = ImageFont.truetype(font_path, font_size)
        text = f"{format(int(timer_value//3600), '02d')}:{format(int(timer_value%3600//60), '02d')}:{format(int(timer_value%60), '02d')}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((image.width - text_width) // 2, (image.height - text_height) // 2 + 35)
        draw.text(position, text, font=font, fill=(0, 0, 0), stroke_width=6, stroke_fill=(255, 255, 255))

        # Add the "Time Left" text
        additional_text = "Time Left".upper()
        additional_font_size = int(100 * 0.32) 
        
        current_path = os.path.dirname(os.path.abspath(__file__))
        #file_path = os.path.join(current_path, '..\\..\\assets\\Mercy Christole.ttf')
        additional_font = ImageFont.truetype(font_path, additional_font_size)
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
        logger.error(f'Error generating timer image: {e}, {tb}')
        return None
    
# Generate an image of the timer with text, color, and time left.
# Utilizes templates for each color state.
# Uses Pillow for image manipulation.
def generate_timer_image(timer_value, timer_duration=43200):
    try:
        # --- Setup ---
        color = get_color_state(timer_value, timer_duration)
        image_number = 6 - (COLOR_STATES.index(color))
        image_path = os.path.join(BASE_DIR, 'assets', f'TheButtonTemplate{image_number:02d}.png')
        font_path = os.path.join(BASE_DIR, 'assets', 'Mercy Christole.ttf')

        if not os.path.exists(image_path) or not os.path.exists(font_path):
            logger.error(f"Asset not found. Image: {image_path}, Font: {font_path}")
            return None

        base_image = Image.open(image_path).convert("RGB")
        
        # --- EMERGENCY TIME THRESHOLDS ---
        emergency_level = "normal"
        if timer_value <= 30:  # Last 30 seconds - ABSOLUTE PANIC
            emergency_level = "apocalypse"
        elif timer_value <= 60:  # Last 1 minute - CRITICAL EMERGENCY
            emergency_level = "critical"
        elif timer_value <= 300:  # Last 5 minutes - EMERGENCY
            emergency_level = "emergency"
        elif timer_value <= 1800:  # Last 30 minutes - HEIGHTENED ALERT
            emergency_level = "alert"
        
        # --- Enhanced Color Personalities ---
        color_index = COLOR_STATES.index(color)
        personalities = {
            0: "panic",      # Red - Frantic emergency mode
            1: "stressed",   # Orange - High anxiety, jittery
            2: "alert",      # Yellow - Watchful, ready to spring
            3: "steady",     # Green - Confident and stable
            4: "serene",     # Blue - Cool and flowing
            5: "royal"       # Purple - Majestic with lots of character (most common!)
        }
        
        personality = personalities[color_index]
        
        # Override personality for emergency situations
        if emergency_level == "apocalypse":
            personality = "apocalypse"
        elif emergency_level == "critical":
            personality = "critical"
        elif emergency_level == "emergency":
            personality = "emergency"
        
        # --- Enhanced Animation Setup ---
        frames = []
        # More frames for emergency modes
        if emergency_level in ["apocalypse", "critical"]:
            num_frames = 40  # Ultra smooth for final moments
            duration_ms = 50  # Very fast
        elif emergency_level == "emergency":
            num_frames = 35  # Smooth emergency
            duration_ms = 60  # Fast
        elif emergency_level == "alert":
            num_frames = 32  # Enhanced alertness
            duration_ms = 65  # Slightly faster
        else:
            num_frames = 30  # Normal
            duration_ms = 70  # Normal speed
        
        # --- Text and Font Setup ---
        font_size = int(120 * 0.32)
        font = ImageFont.truetype(font_path, font_size)
        text = f"{int(timer_value//3600):02d}:{int(timer_value%3600//60):02d}:{int(timer_value%60):02d}"
        
        additional_text = "Time Left".upper()
        additional_font_size = int(100 * 0.32)
        additional_font = ImageFont.truetype(font_path, additional_font_size)
        
        # --- Emoji Setup ---
        emoji_char = get_color_emoji(timer_value, timer_duration)
        emoji_font_path = os.path.join(BASE_DIR, 'assets', 'NotoColorEmoji-Regular.ttf')
        try:
            emoji_font = ImageFont.truetype(emoji_font_path, 45)  # Larger emojis
        except Exception:
            emoji_font = ImageFont.load_default()

        # --- Progress Bar Setup ---
        progress_percentage = timer_value / timer_duration
        bar_y_position = 280
        bar_height = 25
        bar_max_width = 300
        bar_start_x = (base_image.width - bar_max_width) // 2

        for i in range(num_frames):
            frame_image = base_image.copy()
            draw = ImageDraw.Draw(frame_image)

            # --- Enhanced Personality-Based Animation Factors ---
            t = i / num_frames  # Normalized time 0-1
            
            if personality == "apocalypse":
                # APOCALYPSE MODE - Last 30 seconds - ABSOLUTE CHAOS
                chaos_factor = (30 - timer_value) / 30  # 0-1 as we approach zero
                shake_intensity = int(10 + chaos_factor * 15)  # Up to 25 pixels of shake
                
                # Multiple chaotic frequencies
                shake_x = int(
                    math.sin(30 * math.pi * t) * shake_intensity +
                    math.cos(35 * math.pi * t) * (shake_intensity//2) +
                    math.sin(40 * math.pi * t) * (shake_intensity//3)
                )
                shake_y = int(
                    math.cos(32 * math.pi * t) * shake_intensity +
                    math.sin(38 * math.pi * t) * (shake_intensity//2) +
                    math.cos(42 * math.pi * t) * (shake_intensity//3)
                )
                
                # Hyper-intense pulsing
                pulse = (math.sin(25 * math.pi * t) + math.cos(30 * math.pi * t) + 2) / 4
                glow = int(150 + 105 * pulse)  # Maximum glow variation
                text_scale = 1.0 + 0.3 * pulse
                
            elif personality == "critical":
                # CRITICAL MODE - Last 1 minute - EXTREME URGENCY
                critical_factor = (60 - timer_value) / 60
                shake_intensity = int(8 + critical_factor * 8)
                
                shake_x = int(
                    math.sin(25 * math.pi * t) * shake_intensity +
                    math.cos(30 * math.pi * t) * (shake_intensity//2)
                )
                shake_y = int(
                    math.cos(27 * math.pi * t) * shake_intensity +
                    math.sin(32 * math.pi * t) * (shake_intensity//2)
                )
                
                pulse = (math.sin(20 * math.pi * t) + math.cos(22 * math.pi * t) + 2) / 4
                glow = int(160 + 95 * pulse)
                text_scale = 1.0 + 0.25 * pulse
                
            elif personality == "emergency":
                # EMERGENCY MODE - Last 5 minutes - HIGH URGENCY
                emergency_factor = (300 - timer_value) / 300
                shake_intensity = int(6 + emergency_factor * 6)
                
                shake_x = int(
                    math.sin(22 * math.pi * t) * shake_intensity +
                    math.cos(26 * math.pi * t) * (shake_intensity//2)
                )
                shake_y = int(
                    math.cos(24 * math.pi * t) * shake_intensity +
                    math.sin(28 * math.pi * t) * (shake_intensity//2)
                )
                
                pulse = (math.sin(18 * math.pi * t) + math.cos(20 * math.pi * t) + 2) / 4
                glow = int(170 + 85 * pulse)
                text_scale = 1.0 + 0.2 * pulse
                
            elif personality == "panic":
                # Enhanced panic for red with emergency awareness
                base_intensity = 6
                if emergency_level == "alert" :  # 30 minutes - enhanced panic
                    base_intensity = 8
                    
                shake_x = int(math.sin(20 * math.pi * t) * base_intensity + math.cos(25 * math.pi * t) * 2)
                shake_y = int(math.cos(22 * math.pi * t) * base_intensity + math.sin(28 * math.pi * t) * 2)
                pulse = (math.sin(15 * math.pi * t) + 1) / 2
                glow = int(180 + 75 * pulse)
                text_scale = 1.0 + 0.15 * pulse
                
            elif personality == "stressed":
                # Enhanced stress with emergency awareness
                base_intensity = 3
                if emergency_level == "alert":
                    base_intensity = 5
                    
                jitter_x = math.sin(12 * math.pi * t) * base_intensity + math.cos(18 * math.pi * t) * 1.5
                jitter_y = math.cos(14 * math.pi * t) * (base_intensity + 1) + math.sin(16 * math.pi * t) * 2
                shake_x = int(jitter_x)
                shake_y = int(jitter_y)
                pulse = (math.sin(8 * math.pi * t) + math.cos(12 * math.pi * t) + 2) / 4
                glow = int(170 + 50 * pulse)
                text_scale = 1.0 + 0.08 * pulse
                
            elif personality == "alert":
                # Enhanced yellow alertness
                alert_intensity = 2
                if emergency_level == "alert":
                    alert_intensity = 4
                    
                alert_bounce = math.sin(6 * math.pi * t) * alert_intensity
                shake_x = int(math.sin(8 * math.pi * t) * alert_intensity)
                shake_y = int(alert_bounce)
                pulse = (math.sin(5 * math.pi * t) + 1) / 2
                glow = int(185 + 35 * pulse)
                text_scale = 1.0 + 0.05 * pulse
                
            elif personality == "steady":
                # Green remains steady but aware of emergency
                breathe = math.sin(3 * math.pi * t) * 1.5
                sway = math.sin(2 * math.pi * t) * 2
                if emergency_level == "alert":
                    breathe *= 1.5  # Slightly more agitated
                    sway *= 1.3
                    
                shake_x = int(sway)
                shake_y = int(breathe)
                pulse = (math.sin(2.5 * math.pi * t) + 1) / 2
                glow = int(195 + 30 * pulse)
                text_scale = 1.0 + 0.03 * pulse
                
            elif personality == "serene":
                # Blue remains calm but more alert in emergencies
                wave1 = math.sin(2 * math.pi * t) * 2
                wave2 = math.cos(1.5 * math.pi * t) * 1
                if emergency_level == "alert":
                    wave1 *= 1.3
                    wave2 *= 1.2
                    
                shake_x = int(wave1)
                shake_y = int(wave2)
                pulse = (math.sin(1.8 * math.pi * t) + 1) / 2
                glow = int(205 + 25 * pulse)
                text_scale = 1.0 + 0.02 * pulse
                
            else:  # royal (purple)
                # Purple with emergency awareness
                float_primary = math.sin(1.2 * math.pi * t) * 2
                float_secondary = math.cos(1.8 * math.pi * t) * 1.5
                royal_sway = math.sin(0.8 * math.pi * t) * 1
                sparkle_dance = math.cos(2.4 * math.pi * t) * 0.5
                
                if emergency_level == "alert":
                    # Royal urgency - more dramatic movements
                    float_primary *= 1.5
                    float_secondary *= 1.3
                    royal_sway *= 1.4
                
                shake_x = int(royal_sway + sparkle_dance)
                shake_y = int(float_primary + float_secondary)
                
                pulse_base = (math.sin(1.3 * math.pi * t) + 1) / 2
                pulse_sparkle = (math.cos(2.1 * math.pi * t) + 1) / 2
                pulse = (pulse_base * 0.7 + pulse_sparkle * 0.3)
                
                glow = int(210 + 45 * pulse)
                text_scale = 1.0 + 0.025 * pulse

            # --- Enhanced Color Variations with Emergency Modes ---
            r, g, b = color
            
            if personality in ["apocalypse", "critical", "emergency"]:
                # EMERGENCY COLOR OVERRIDE - Intense red/white flashing
                if personality == "apocalypse":
                    # White-hot flashing for apocalypse
                    flash_intensity = int(pulse * 60)
                    white_flash = int(pulse * 100)
                    bar_color = (
                        min(255, 255),  # Pure red channel
                        min(255, white_flash),  # White flash on green
                        min(255, white_flash)   # White flash on blue
                    )
                elif personality == "critical":
                    # Intense red with white hot spots
                    flash_intensity = int(pulse * 50)
                    white_flash = int(pulse * 70)
                    bar_color = (255, min(255, white_flash//2), min(255, white_flash//2))
                else:  # emergency
                    # Enhanced red with orange flashing
                    flash_intensity = int(pulse * 40)
                    orange_flash = int(pulse * 30)
                    bar_color = (255, min(255, orange_flash), max(0, orange_flash//3))
                    
            elif personality == "panic":
                # Enhanced panic colors
                flash = int(pulse * 40)
                white_hot = int(pulse * 20)
                if emergency_level == "alert":
                    flash += 15
                    white_hot += 10
                bar_color = (min(255, r + flash + white_hot), max(0, g - flash//2 + white_hot), max(0, b - flash//2 + white_hot))
            elif personality == "stressed":
                # Enhanced stress colors
                warm_flicker = int(pulse * 25)
                stress_red = int(pulse * 15)
                if emergency_level == "alert":
                    warm_flicker += 10
                    stress_red += 8
                bar_color = (min(255, r + stress_red), min(255, g + warm_flicker), max(0, b - warm_flicker//2))
            elif personality == "alert":
                # Enhanced alert colors
                brightness = int(pulse * 20)
                if emergency_level == "alert":
                    brightness += 15
                bar_color = (min(255, r + brightness), min(255, g + brightness), max(0, b - brightness//3))
            elif personality == "steady":
                # Green with emergency awareness
                vitality = int(pulse * 12)
                if emergency_level == "alert":
                    vitality += 8
                bar_color = (max(0, r - vitality//3), min(255, g + vitality), max(0, b - vitality//2))
            elif personality == "serene":
                # Blue with emergency shimmer
                cool_shimmer = int(pulse * 15)
                if emergency_level == "alert":
                    cool_shimmer += 10
                bar_color = (max(0, r - cool_shimmer//2), max(0, g - cool_shimmer//3), min(255, b + cool_shimmer))
            else:  # royal
                # Royal with emergency urgency
                royal_shimmer = int(pulse * 30)
                gold_highlight = int(pulse_sparkle * 20)
                magic_boost = int((pulse + pulse_sparkle) * 10)
                
                if emergency_level == "alert":
                    royal_shimmer += 15
                    gold_highlight += 10
                
                bar_color = (
                    min(255, r + royal_shimmer//2 + gold_highlight),
                    max(0, g - royal_shimmer//4 + gold_highlight//2),
                    min(255, b + royal_shimmer + magic_boost)
                )

            # --- Enhanced Progress Bar with Strong Personality ---
            def draw_rounded_rectangle(draw_context, xy, corner_radius, fill_color):
                x1, y1, x2, y2 = xy
                if len(fill_color) == 4:
                    fill_color = fill_color[:3]
                    
                draw_context.rectangle([x1 + corner_radius, y1, x2 - corner_radius, y2], fill=fill_color)
                draw_context.rectangle([x1, y1 + corner_radius, x2, y2 - corner_radius], fill=fill_color)
                draw_context.pieslice([x1, y1, x1 + corner_radius * 2, y1 + corner_radius * 2], 180, 270, fill=fill_color)
                draw_context.pieslice([x2 - corner_radius * 2, y1, x2, y1 + corner_radius * 2], 270, 360, fill=fill_color)
                draw_context.pieslice([x1, y2 - corner_radius * 2, x1 + corner_radius * 2, y2], 90, 180, fill=fill_color)
                draw_context.pieslice([x2 - corner_radius * 2, y2 - corner_radius * 2, x2, y2], 0, 90, fill=fill_color)

            # Background bar with emergency intensity
            bar_bg_color = (25, 25, 25)
            current_bar_width = int(bar_max_width * progress_percentage)
            radius = 10
            
            # Emergency bar animations
            if personality in ["apocalypse", "critical", "emergency"]:
                if personality == "apocalypse":
                    bar_height_mod = bar_height + int(pulse * 8)
                    bar_y_mod = bar_y_position - int(pulse * 4)
                elif personality == "critical":
                    bar_height_mod = bar_height + int(pulse * 6)
                    bar_y_mod = bar_y_position - int(pulse * 3)
                else:  # emergency
                    bar_height_mod = bar_height + int(pulse * 5)
                    bar_y_mod = bar_y_position - int(pulse * 2.5)
            elif personality == "panic":
                expansion = 5 if emergency_level == "alert" else 5
                bar_height_mod = bar_height + int(pulse * expansion)
                bar_y_mod = bar_y_position - int(pulse * (expansion//2))
            elif personality == "royal":
                royal_expansion = int((pulse + pulse_sparkle) * 2)
                if emergency_level == "alert":
                    royal_expansion = int(royal_expansion * 1.5)
                bar_height_mod = bar_height + royal_expansion
                bar_y_mod = bar_y_position - royal_expansion//2
            else:
                expansion = 2 if emergency_level == "alert" else 1
                bar_height_mod = bar_height + int(pulse * expansion)
                bar_y_mod = bar_y_position
            
            bg_coords = [bar_start_x, bar_y_mod, bar_start_x + bar_max_width, bar_y_mod + bar_height_mod]
            draw_rounded_rectangle(draw, bg_coords, radius, bar_bg_color)

            if current_bar_width > radius * 2:
                fg_coords = [bar_start_x, bar_y_mod, bar_start_x + current_bar_width, bar_y_mod + bar_height_mod]
                draw_rounded_rectangle(draw, fg_coords, radius, bar_color)

            # --- GREATLY Enhanced Emergency Emoji Animation ---
            if personality in ["apocalypse", "critical", "emergency"]:
                if personality == "apocalypse":
                    emoji_bounce = int(math.sin(25 * math.pi * t) * 15 + math.cos(30 * math.pi * t) * 10)
                    emoji_wiggle = int(math.cos(28 * math.pi * t) * 12 + math.sin(32 * math.pi * t) * 8)
                elif personality == "critical":
                    emoji_bounce = int(math.sin(20 * math.pi * t) * 12 + math.cos(25 * math.pi * t) * 8)
                    emoji_wiggle = int(math.cos(22 * math.pi * t) * 10 + math.sin(26 * math.pi * t) * 6)
                else:  # emergency
                    emoji_bounce = int(math.sin(18 * math.pi * t) * 10 + math.cos(22 * math.pi * t) * 6)
                    emoji_wiggle = int(math.cos(20 * math.pi * t) * 8 + math.sin(24 * math.pi * t) * 4)
            elif personality == "panic":
                base_bounce = 10 if emergency_level == "alert" else 10
                base_wiggle = 6 if emergency_level == "alert" else 6
                emoji_bounce = int(math.sin(15 * math.pi * t) * base_bounce + math.cos(18 * math.pi * t) * 5)
                emoji_wiggle = int(math.cos(16 * math.pi * t) * base_wiggle + math.sin(20 * math.pi * t) * 3)
            elif personality == "stressed":
                base_multiplier = 1.3 if emergency_level == "alert" else 1.0
                emoji_bounce = int((math.sin(10 * math.pi * t) * 6 + math.cos(12 * math.pi * t) * 3) * base_multiplier)
                emoji_wiggle = int((math.sin(11 * math.pi * t) * 4 + math.cos(14 * math.pi * t) * 2) * base_multiplier)
            elif personality == "alert":
                base_multiplier = 1.5 if emergency_level == "alert" else 1.0
                emoji_bounce = int(math.sin(6 * math.pi * t) * 4 * base_multiplier)
                emoji_wiggle = int(math.cos(7 * math.pi * t) * 2 * base_multiplier)
            elif personality == "steady":
                base_multiplier = 1.2 if emergency_level == "alert" else 1.0
                emoji_bounce = int(math.sin(3 * math.pi * t) * 3 * base_multiplier)
                emoji_wiggle = int(math.cos(2.5 * math.pi * t) * 2 * base_multiplier)
            elif personality == "serene":
                base_multiplier = 1.15 if emergency_level == "alert" else 1.0
                emoji_bounce = int(math.sin(2 * math.pi * t) * 2 * base_multiplier)
                emoji_wiggle = int(math.cos(1.8 * math.pi * t) * 1.5 * base_multiplier)
            else:  # royal
                multiplier = 1.4 if emergency_level == "alert" else 1.0
                royal_float = int((math.sin(1.2 * math.pi * t) * 4 + math.cos(1.8 * math.pi * t) * 2) * multiplier)
                royal_sway = int((math.sin(0.9 * math.pi * t) * 3 + math.cos(1.4 * math.pi * t) * 1.5) * multiplier)
                sparkle_twirl = int(math.sin(2.4 * math.pi * t) * 1 * multiplier)
                
                emoji_bounce = royal_float + sparkle_twirl
                emoji_wiggle = royal_sway

            emoji_y_pos = bar_y_mod - 25 + emoji_bounce
            emoji_x_left = bar_start_x - 70 + emoji_wiggle
            emoji_x_right = bar_start_x + bar_max_width + 70 - emoji_wiggle

            # Draw emojis or enhanced fallback circles
            try:
                draw.text((emoji_x_left, emoji_y_pos), emoji_char, font=emoji_font, fill=(255, 255, 255))
                draw.text((emoji_x_right, emoji_y_pos), emoji_char, font=emoji_font, fill=(255, 255, 255))
            except Exception:
                if personality == "royal":
                    circle_radius = int(20 + pulse * 5)
                    inner_radius = int(circle_radius * 0.7)
                    draw.ellipse([emoji_x_left - circle_radius, emoji_y_pos - circle_radius,
                                 emoji_x_left + circle_radius, emoji_y_pos + circle_radius], fill=bar_color)
                    sparkle_color = (min(255, bar_color[0] + 30), min(255, bar_color[1] + 20), min(255, bar_color[2] + 40))
                    draw.ellipse([emoji_x_left - inner_radius, emoji_y_pos - inner_radius,
                                 emoji_x_left + inner_radius, emoji_y_pos + inner_radius], fill=sparkle_color)
                    draw.ellipse([emoji_x_right - circle_radius, emoji_y_pos - circle_radius,
                                 emoji_x_right + circle_radius, emoji_y_pos + circle_radius], fill=bar_color)
                    draw.ellipse([emoji_x_right - inner_radius, emoji_y_pos - inner_radius,
                                 emoji_x_right + inner_radius, emoji_y_pos + inner_radius], fill=sparkle_color)
                else:
                    circle_radius = int(18 + pulse * 4)
                    draw.ellipse([emoji_x_left - circle_radius, emoji_y_pos - circle_radius,
                                 emoji_x_left + circle_radius, emoji_y_pos + circle_radius], fill=bar_color)
                    draw.ellipse([emoji_x_right - circle_radius, emoji_y_pos - circle_radius,
                                 emoji_x_right + circle_radius, emoji_y_pos + circle_radius], fill=bar_color)

            # --- Emergency Enhanced Text Rendering ---
            text_bbox = font.getbbox(text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            base_text_pos = ((base_image.width - text_width) // 2, (base_image.height - text_height) // 2 + 35)
            
            additional_text_bbox = additional_font.getbbox(additional_text)
            additional_text_width = additional_text_bbox[2] - additional_text_bbox[0]
            base_additional_pos = ((base_image.width - additional_text_width) // 2, 70)

            text_pos = (base_text_pos[0] + shake_x, base_text_pos[1] + shake_y)
            additional_text_pos = (base_additional_pos[0] + shake_x, base_additional_pos[1] + shake_y)

            # Emergency stroke effects
            if personality in ["apocalypse", "critical", "emergency"]:
                if personality == "apocalypse":
                    stroke_width = 15
                    stroke_color = (255, 255, min(255, int(glow * 1.5)))  # White-hot glow
                elif personality == "critical":
                    stroke_width = 14
                    stroke_color = (255, min(255, int(glow * 1.4)), min(255, int(glow * 1.4)))
                else:  # emergency
                    stroke_width = 13
                    stroke_color = (255, min(255, int(glow * 1.3)), min(255, int(glow * 1.2)))
            elif personality == "panic":
                stroke_width = 12 if emergency_level == "alert" else 12
                stroke_color = (255, min(255, int(glow * 1.3)), min(255, int(glow * 1.3)))
            elif personality == "stressed":
                stroke_width = 11 if emergency_level == "alert" else 10
                stroke_color = (min(255, int(glow * 1.2)), min(255, int(glow * 1.1)), min(255, int(glow)))
            elif personality == "royal":
                stroke_width = 10 if emergency_level == "alert" else 9
                gold_shimmer = int(pulse_sparkle * 40)
                if emergency_level == "alert":
                    gold_shimmer += 20
                stroke_color = (
                    min(255, int(glow * 0.9) + gold_shimmer//2),
                    min(255, int(glow * 0.8) + gold_shimmer//3),
                    min(255, int(glow * 1.2))
                )
            else:
                stroke_width = 8 if emergency_level == "alert" else 7
                stroke_color = (glow, glow, glow)
            
            text_color = (0, 0, 0)
            
            draw.text(text_pos, text, font=font, fill=text_color, stroke_width=stroke_width, stroke_fill=stroke_color)
            draw.text(additional_text_pos, additional_text, font=additional_font, fill=text_color, stroke_width=stroke_width, stroke_fill=stroke_color)

            if frame_image.mode != 'RGB':
                frame_image = frame_image.convert('RGB')
                
            frames.append(frame_image)

        # --- Optimized GIF Creation ---
        buffer = BytesIO()
        
        palette_frames = []
        for frame in frames:
            palette_frame = frame.convert('P', palette=Image.ADAPTIVE, colors=256)
            palette_frames.append(palette_frame)
        
        palette_frames[0].save(
            buffer, 
            format='GIF', 
            save_all=True, 
            append_images=palette_frames[1:], 
            duration=duration_ms, 
            loop=0,
            disposal=0,
            optimize=False
        )
        buffer.seek(0)

        return File(buffer, filename='timer.gif')
        
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f'Error generating timer image: {e}, {tb}')
        return None

print("Utils file loaded.")

if __name__ == "__main__":
    # Test the generate_timer_image function
    test_image = generate_timer_image(10000, 43200)
    if test_image:
        print("Timer image generated successfully.")
    else:
        print("Failed to generate timer image.")

    # Save the gif result
    with open('test_timer.gif', 'wb') as f:
        f.write(test_image.fp.getbuffer())