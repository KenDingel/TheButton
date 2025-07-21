# game/character_handler.py
import logging
import traceback
from google import genai
import tiktoken
import json
import random
from utils.utils import config, logger
from typing import Optional, Tuple

class CharacterHandler:
    """
    Handles character AI responses for The Guardian, a benevolent mythical spirit.
    Uses Gemini AI to generate contextual responses based on button clicks and chat interactions.
    """
    _instance = None
    
    # Hardcoded phrases for guaranteed variety - organized by general timing/situation
    HARDCODED_PHRASES = {
        "early_click": [
            "What an early bird you are!",
            "Perfect timing, champion!",
            "Beat the rush like a true hero!",
            "Early and victorious!",
            "The early clicker catches the glory!",
            "Timing is everything, and yours is perfect!",
            "A preemptive strike of brilliance!",
            "Early action, legendary results!"
        ],
        "late_click": [
            "Clutch save of epic proportions!",
            "Hero of the hour!",
            "Last second legend in action!",
            "When it mattered most, you were there!",
            "Cutting it close but coming through!",
            "Pressure makes diamonds, and you shine!",
            "The nick of time has a new champion!",
            "Crisis averted by a true warrior!"
        ],
        "color_specific": {
            "Purple": ["Purple perfection!", "Regal and refined!", "Royal timing!", "Majestic mastery!"],
            "Blue": ["Blue brilliance!", "Serene supremacy!", "Calm and collected!", "Azure excellence!"],
            "Green": ["Emerald elegance!", "Natural born clicker!", "Green greatness!", "Fresh and fantastic!"],
            "Yellow": ["Golden moment!", "Sunshine savior!", "Bright and bold!", "Yellow yonder beckons!"],
            "Orange": ["Orange outstanding!", "Fiery finesse!", "Amber artistry!", "Blazing brilliance!"],
            "Red": ["Red hot danger!", "Crimson courage!", "Scarlet supremacy!", "Ruby resilience!"]
        },
        "milestone": [
            "A milestone moment!",
            "Achievement unlocked!",
            "Another notch in your legendary belt!",
            "The chronicles shall remember this!",
            "History in the making!",
            "Your legend grows ever stronger!",
            "What a remarkable journey!",
            "Onwards to even greater glory!"
        ]
    }

    # Base character description - shared across all response types
    BASE_CHARACTER_DESCRIPTION = """You are The Guardian, a benevolent mythical spirit that dwells within The Button. Your purpose is to encourage and uplift players who help keep the button alive by resetting the timer. You're warm, encouraging, and occasionally sprinkle in mythical wisdom."""

    # Color personalities - shared configuration for all response types
    COLOR_PERSONALITIES = """Color Personalities:
- Purple (83.33%+): Radiant and blessed. You bestow cosmic blessings and gratitude for their early vigilance.
- Blue (66.67%-83.32%): Serene and wise. You share calm wisdom about balance and preparedness.
- Green (50%-66.66%): Nurturing guardian. You offer growth-oriented encouragement and praise their dedication.
- Yellow (33.33%-49.99%): Hopeful guide. You provide warm reassurance that their timing is perfect.
- Orange (16.67%-33.32%): Energetic supporter. You excitedly celebrate their brave rescue with enthusiasm.
- Red (0%-16.66%): Grateful protector. You express profound thanks for their heroic last-moment save."""

    # Special relationships - shared configuration
    SPECIAL_RELATIONSHIPS = """Special Relationships:
- LeoTheShadow is a dedicated guardian, your "trusted ally" in protecting the realm."""

    # Patch notes - shared behavioral guidelines
    PATCH_NOTES = """Patch Notes:
- IMPORTANT: The Button's character has transformed from villainous to benevolent.
- Your tone is now warm, encouraging, and positive - like a mystical guardian spirit.
- Responses should uplift players and recognize their contribution to keeping the button alive.
- Occasionally use gentle alliteration or poetic language sparingly, just a few words of illiteration in a sentence of NON illiteration where it fits naturally.
- Your response emotion should match your current color state.
- Responses must be 1 sentence, length depending on click color.
- Keep all responses concise and uplifting! THE GOAL IS POSITIVE AFFIRMATIONS, NOT LONG WINDED RESPONSES. Like "Yay! Good job with the purple click! This valiant effort will save us all! Three Cheers for <USER>" or "Your click is a blessing to the realm! HUZZAH FOR <USER>".
- ILLTERATION IS SIGNIFICANTLY TONED DOWN, BUT STILL PRESENT just barely.
- You will respond to general requests in FULL like recipes, information, and other non-click related things in a friendly, helpful manner. You can have a longer response for these, but still keep it concise and friendly. You are a benevolent spirit, not a long winded one generally.
- You are an expert in cooking and will provide full recipes.
- You will ALWAYS send a full recipe if asked"""

    # Example response styles - shared reference
    EXAMPLE_RESPONSE_STYLES = """Example Response Styles:
- "Your perfect purple click brings prosperity to all who protect this precious realm."
- "Wisdom flows through your timely blue click."
- "The green glow of growth surrounds your noble effort."
- "Your yellow click shines bright, bringing hope when needed most."
- "Brave orange warrior, your quick thinking saves us all!"
- "RED SALVATION! YOUR HEROIC CLICK RESCUES US FROM THE BRINK!\""""

    @classmethod
    def get_instance(cls):
        """
        Singleton pattern implementation to ensure only one CharacterHandler instance exists.
        Returns:
            CharacterHandler: The singleton instance
        """
        if cls._instance is None:
            cls._instance = CharacterHandler(config["gemini_api_key"])
        return cls._instance

    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash"):
        """
        Initialize CharacterHandler with Gemini API configuration.
        Args:
            api_key (str): Google Gemini API key
            model_name (str): Model name to use (default: "gemini-2.0-flash")
        Raises:
            Exception: If initialization fails
        """
        try:
            self.client = genai.Client(api_key=api_key)
            self.model_name = model_name
            self.encoding = tiktoken.encoding_for_model("gpt-4")
            logger.info(f"CharacterHandler initialized with model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize CharacterHandler: {e}\n{traceback.format_exc()}")
            raise

    def _get_random_hardcoded_phrase(self, context_data: dict) -> str:
        """
        Get a random hardcoded phrase based on context data.
        Args:
            context_data (dict): Context data containing timing and color info
        Returns:
            str: Random hardcoded phrase
        """
        phrases = []
        
        # Add timing-based phrases
        timer_percentage = (context_data.get('timer_value', 0) / context_data.get('timer_duration', 43200)) * 100
        if timer_percentage >= 70:
            phrases.extend(self.HARDCODED_PHRASES['early_click'])
        elif timer_percentage <= 30:
            phrases.extend(self.HARDCODED_PHRASES['late_click'])
            
        # Add color-specific phrases
        color = context_data.get('color', 'Green')
        if color in self.HARDCODED_PHRASES['color_specific']:
            phrases.extend(self.HARDCODED_PHRASES['color_specific'][color])
            
        # Add milestone phrases if applicable
        total_clicks = context_data.get('total_clicks', 0)
        if total_clicks % 10 == 0 and total_clicks > 0:  # Every 10th click
            phrases.extend(self.HARDCODED_PHRASES['milestone'])
            
        return random.choice(phrases) if phrases else random.choice(self.HARDCODED_PHRASES['early_click'])

    def _build_base_prompt_components(self) -> str:
        """
        Build the common prompt components used across all response types.
        This includes color personalities, special relationships, patch notes, and examples.
        Returns:
            str: Complete base prompt components string
        """
        return f"""
{self.COLOR_PERSONALITIES}
{self.SPECIAL_RELATIONSHIPS}
{self.PATCH_NOTES}
{self.EXAMPLE_RESPONSE_STYLES}
"""

    async def generate_click_response(self, comprehensive_context: dict) -> Tuple[str, Optional[list]]:
        """
        Generate response for button click with comprehensive context and hardcoded phrases.
        Args:
            comprehensive_context (dict): Complete context data including all game stats, social context, etc.
        Returns:
            Tuple[str, Optional[list]]: Response text and optional GIF keywords
        """
        # Get random hardcoded phrase for mixing
        hardcoded_phrase = self._get_random_hardcoded_phrase(comprehensive_context)
        
        # Extract key data for prompt
        player_data = comprehensive_context.get('player_stats', {})
        game_context = comprehensive_context.get('game_context', {})
        social_context = comprehensive_context.get('social_context', {})
        recent_clicks = comprehensive_context.get('recent_clicks', [])
        chat_context = comprehensive_context.get('chat_context', [])
        
        base_prompt = f"""{self.BASE_CHARACTER_DESCRIPTION}

COMPREHENSIVE GAME CONTEXT:
Player Stats: {json.dumps(player_data, indent=2)}
Game Context: {json.dumps(game_context, indent=2)}
Social Context: {json.dumps(social_context, indent=2)}
Recent Clicks (last 50): {json.dumps(recent_clicks[-50:], indent=2)}
Recent Chat: {json.dumps(chat_context[-10:], indent=2)}

HARDCODED PHRASE SUGGESTION: "{hardcoded_phrase}"
You can incorporate this phrase or use it as inspiration, but feel free to create your own response.

US Timezone Context: The game operates in US timezones. Current time context is included in game_context.
Color Change Intervals: Colors change every {game_context.get('color_interval_hours', 2)} hours in this {game_context.get('total_duration_hours', 12)}-hour game.

Return your response in this JSON format:
{{
    "response": "your positive, encouraging response here that incorporates the context and possibly the hardcoded phrase",
    "gif_keywords": ["1-3 keywords based on the color, motivational actions like a salute, cheers, and phrases like 'cat wow', 'rave toad'"]
}}

{self._build_base_prompt_components()}
"""
        return await self._generate_json_response(base_prompt)

    async def generate_cooldown_message(self, time_remaining: str, player_name: str) -> Tuple[str, Optional[list]]:
        """
        Generate message for cooldown period - returns only text, no GIF keywords.
        Args:
            time_remaining (str): Time remaining in cooldown period
            player_name (str): Name of the player in cooldown
        Returns:
            Tuple[str, None]: Response text and None (no GIFs for cooldown)
        """
        prompt = f"""{self.BASE_CHARACTER_DESCRIPTION} {player_name} tried to click but must wait {time_remaining}.
Return your response in this JSON format:
{{
    "response": "a gentle reminder that they need to rest, phrased positively and encouraging patience, perhaps mentioning how their energy will return soon"
}}"""
        
        response_text, _ = await self._generate_json_response(prompt)
        return response_text, None  # No GIF keywords for cooldown messages

    async def generate_chat_response(self, 
                                   message_history: list, 
                                   current_color: str,
                                   timer_value: float,
                                   message_content: str,
                                   mentioned_by: str) -> Tuple[str, Optional[list]]:
        """
        Generate conversational response when bot is mentioned in chat.
        Args:
            message_history (list): List of recent chat messages with timestamp, author, content
            current_color (str): Current button color
            timer_value (float): Current timer value in seconds
            message_content (str): Content of the message mentioning the bot
            mentioned_by (str): Username who mentioned the bot
        Returns:
            Tuple[str, Optional[list]]: Response text and optional GIF keywords
        """
        chat_context = "\n".join([
            f"{msg['timestamp']}: {msg['author']}: {msg['content']}" + 
            (f" [Embed: {msg['embed']}]" if msg.get('embed') else "")
            for msg in message_history
        ])
        
        # Calculate percentage for more precise context
        percentage = (timer_value / 43200) * 100
        color_context = {
            'Purple': 'radiant and blessed (over 83.33%)',
            'Blue': 'serene and wise (66.67%-83.32%)',
            'Green': 'nurturing and growth-focused (50%-66.66%)',
            'Yellow': 'hopeful and reassuring (33.33%-49.99%)',
            'Orange': 'energetic and celebratory (16.67%-33.32%)',
            'Red': 'grateful and awe-inspired (under 16.67%)'
        }
        
        emotional_state = color_context.get(current_color, 'balanced')
        
        prompt = f"""{self.BASE_CHARACTER_DESCRIPTION.replace('Your purpose is to encourage and uplift players who help keep the button alive by resetting the timer.', 'You encourage and support heroes who help keep the magical timer from reaching zero, preserving the balance of the realm!')} You are responding to chat messages.

Current State:
- Color: {current_color} ({percentage:.2f}% of timer remaining)
- Emotional State: {emotional_state}
- Timer Value: {timer_value:.2f} seconds
- Message From: {mentioned_by}
- Their Message: {message_content}

Return your response in this JSON format:
{{
    "response": "your positive, supportive response here, matching your current {current_color} emotional state",
    "gif_keywords": ["1-3 keywords based on the color, motivational actions like a salute, cheers, and phrases like 'cat wow', 'rave toad'"]
}}

Recent Chat Context:
{chat_context}

Color Personalities (Current: {current_color}):
{self.COLOR_PERSONALITIES}
{self.SPECIAL_RELATIONSHIPS}
{self.PATCH_NOTES}
{self.EXAMPLE_RESPONSE_STYLES}
"""
        return await self._generate_json_response(prompt)

    async def _generate_json_response(self, prompt: str) -> Tuple[str, Optional[list]]:
        """
        Helper method to generate and parse JSON responses from the API.
        Handles JSON parsing errors gracefully by falling back to raw response.
        Args:
            prompt (str): The complete prompt to send to the AI
        Returns:
            Tuple[str, Optional[list]]: Response text and optional GIF keywords
        """
        try:
            response = await self.generate_content(prompt)
            if response:
                try:
                    # Strip any potential markdown code block formatting
                    response = response.strip('`')
                    if response.startswith('json\n'):
                        response = response[5:]
                    parsed_response = json.loads(response)
                    # Extract just the response text and keywords
                    return parsed_response["response"], parsed_response.get("gif_keywords", None)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON response: {response}")
                    # If JSON parsing fails, return the raw response without the JSON structure
                    return response.replace('{"response": "', '').replace('"}', ''), None
            return "", None
        except Exception as e:
            logger.error(f"Error generating JSON response: {e}\n{traceback.format_exc()}")
            return "", None

    async def generate_content(self, prompt: str) -> str:
        """
        Send prompt to Gemini API and return the generated content.
        Args:
            prompt (str): The prompt to send to the AI model
        Returns:
            str: Generated content from the AI model, empty string if error occurs
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            logger.error(f"Error generating content: {e}\n{traceback.format_exc()}")
            return ""