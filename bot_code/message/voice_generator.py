import os
import requests
import time
import uuid
import logging
import traceback
from pathlib import Path
from utils.utils import logger, config

API_KEY = config['ELEVEN_LABS_API_KEY']
OUTPUT_DIR = config['ELEVEN_LABS_OUTPUT_DIR']
DEFAULT_VOICE_ID = config['DEFAULT_VOICE_ID']

class ElevenLabsTTS:
    """
    A class to interact with the Eleven Labs Text-to-Speech API.
    
    This class provides functionality to convert text to speech using the Eleven Labs API
    and save the resulting audio locally.
    """
    
    # Base URL for the Eleven Labs API
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    def __init__(self, api_key=API_KEY, output_dir="audio_output", default_voice_id=DEFAULT_VOICE_ID):
        """
        Initialize the ElevenLabsTTS client.
        
        Parameters:
            api_key (str, optional): Eleven Labs API key. If not provided, will look for ELEVEN_LABS_API_KEY environment variable.
            output_dir (str, optional): Directory to save audio files. Defaults to "audio_output".
            default_voice_id (str, optional): Default voice ID to use. Defaults to "DEFAULT_VOICE_ID" (Rachel voice).
        """
        # Use provided API key or get from environment
        self.api_key = api_key or API_KEY
        if not self.api_key:
            logger.error("No API key provided. Set ELEVEN_LABS_API_KEY environment variable or pass api_key parameter.")
            raise ValueError("Eleven Labs API key is required")
        
        # Set up output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Audio files will be saved to {self.output_dir.absolute()}")
        
        # Set default voice ID
        self.default_voice_id = default_voice_id
    
    def text_to_speech(self, text, voice_id=None, model_id="eleven_monolingual_v1", filename=None):
        """
        Convert text to speech using Eleven Labs API.
        
        Parameters:
            text (str): The text to convert to speech.
            voice_id (str, optional): Voice ID to use. Defaults to the instance's default_voice_id.
            model_id (str, optional): Model ID to use. Defaults to "eleven_monolingual_v1".
            filename (str, optional): Custom filename for the saved audio. If not provided, a UUID will be generated.
            
        Returns:
            str: Path to the saved audio file or None if the operation failed.
        """
        if not text:
            logger.warning("Empty text provided, cannot generate speech")
            return None
            
        voice_id = voice_id or self.default_voice_id
        
        try:
            logger.info(f"Converting text to speech: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # Prepare API request
            url = f"{self.BASE_URL}/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            # Make API request
            start_time = time.time()
            logger.info(f"Sending request to Eleven Labs API (voice: {voice_id}, model: {model_id})")
            response = requests.post(url, headers=headers, json=data)
            
            # Check if request was successful
            if response.status_code != 200:
                logger.error(f"API request failed with status code {response.status_code}: {response.text}")
                return None
                
            # Generate filename if not provided
            if not filename:
                filename = f"tts_{uuid.uuid4()}.mp3"
            elif not filename.endswith(".mp3"):
                filename = f"{filename}.mp3"
                
            # Save audio file
            file_path = self.output_dir / filename
            with open(file_path, "wb") as audio_file:
                audio_file.write(response.content)
                
            elapsed_time = time.time() - start_time
            logger.info(f"Audio saved to {file_path} (generated in {elapsed_time:.2f}s)")
            
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error generating speech: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def list_available_voices(self):
        """
        List all available voices from Eleven Labs API.
        
        Returns:
            list: List of available voice dictionaries or None if the operation failed.
        """
        try:
            url = f"{self.BASE_URL}/voices"
            headers = {"xi-api-key": self.api_key}
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to retrieve voices: {response.status_code} - {response.text}")
                return None
                
            voices = response.json().get("voices", [])
            logger.info(f"Retrieved {len(voices)} available voices")
            return voices
            
        except Exception as e:
            logger.error(f"Error listing voices: {str(e)}")
            logger.error(traceback.format_exc())
            return None


def generate_audio(text, api_key=None, voice_id=None, output_dir=None, filename=None):
    """
    Convenience function to generate audio from text using Eleven Labs API.
    
    Parameters:
        text (str): The text to convert to speech.
        api_key (str, optional): Eleven Labs API key. If not provided, will look for ELEVEN_LABS_API_KEY environment variable.
        voice_id (str, optional): Voice ID to use. If not provided, will use the default voice.
        output_dir (str, optional): Directory to save audio files. Defaults to "audio_output".
        filename (str, optional): Custom filename for the saved audio. If not provided, a UUID will be generated.
        
    Returns:
        str: Path to the saved audio file or None if the operation failed.
    """
    try:
        tts = ElevenLabsTTS(api_key=api_key, output_dir=output_dir or "audio_output")
        return tts.text_to_speech(text, voice_id=voice_id, filename=filename)
    except Exception as e:
        logger.error(f"Error in generate_audio: {str(e)}")
        logger.error(traceback.format_exc())
        return None
    
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert text to speech using Eleven Labs API")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument("--voice-id", help="Voice ID to use (default is Rachel voice)")
    
    args = parser.parse_args()
    
    audio_path = generate_audio(
        args.text,
        voice_id=args.voice_id
    )
    
    if audio_path:
        print(f"Audio generated successfully: {audio_path}")
    else:
        print("Failed to generate audio. Check logs for details.")