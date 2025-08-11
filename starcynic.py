#!/usr/bin/env python3
"""
StarCynic - Skip Edition
A sarcastic but helpful AI copilot for Star Citizen

Author: Your Name
Version: 1.0.0
License: MIT
"""

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import tempfile
import io

# Core dependencies
import requests
from dataclasses import dataclass, asdict
import edge_tts
import pygame

# Wingman imports (these will be available in the Wingman environment)
try:
    from api.interface import SkillConfig, WingmanInitializationError
    from services.audio_player import AudioPlayer
    from services.websocket_server import WebSocketServer
    WINGMAN_AVAILABLE = True
except ImportError:
    # For development/testing outside Wingman
    WINGMAN_AVAILABLE = False
    print("Running outside Wingman environment - some features disabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SessionState:
    """Track comprehensive session state for dynamic responses"""
    last_death_time: float = 0
    last_cargo_loss_time: float = 0
    last_advice_type: str = ""
    ignored_advice: bool = False
    consecutive_roasts: int = 0
    serious_mode_until: float = 0
    total_deaths: int = 0
    total_cargo_losses: int = 0
    last_interaction_time: float = 0
    last_response: str = ""
    session_start_time: float = 0
    
    # Enhanced memory for dynamic responses
    recent_responses: List[str] = None
    pilot_skill_level: str = "unknown"  # novice, intermediate, expert
    favorite_activities: List[str] = None  # trading, combat, exploration, mining
    current_ship: str = "unknown"
    current_location: str = "unknown"
    current_mission: str = ""
    successful_landings: int = 0
    failed_landings: int = 0
    quantum_jumps_completed: int = 0
    times_helped_with: Dict[str, int] = None
    personality_notes: List[str] = None  # Things Skip has learned about the pilot
    
    def __post_init__(self):
        if self.recent_responses is None:
            self.recent_responses = []
        if self.favorite_activities is None:
            self.favorite_activities = []
        if self.times_helped_with is None:
            self.times_helped_with = {}
        if self.personality_notes is None:
            self.personality_notes = []

class ToneDecider:
    """Calculates roast probability based on context"""
    
    BASE_ROAST_PROBABILITY = 40
    
    @classmethod
    def calculate_roast_probability(cls, state: SessionState, event_type: str) -> int:
        """Calculate roast probability based on session context"""
        prob = cls.BASE_ROAST_PROBABILITY
        current_time = time.time()
        
        # Time-based modifiers
        minutes_since_death = (current_time - state.last_death_time) / 60 if state.last_death_time > 0 else 999
        minutes_since_cargo_loss = (current_time - state.last_cargo_loss_time) / 60 if state.last_cargo_loss_time > 0 else 999
        
        # Context modifiers
        if minutes_since_death <= 5:
            prob += 25
            logger.info(f"Recent death modifier: +25% (death {minutes_since_death:.1f}m ago)")
            
        if minutes_since_cargo_loss <= 10:
            prob += 30
            logger.info(f"Recent cargo loss modifier: +30% (loss {minutes_since_cargo_loss:.1f}m ago)")
            
        if state.ignored_advice:
            prob += 35
            logger.info("Ignored advice modifier: +35%")
            
        if state.consecutive_roasts > 0:
            prob += 15
            logger.info(f"Roast momentum modifier: +15% ({state.consecutive_roasts} consecutive)")
            
        # Serious mode override
        if current_time < state.serious_mode_until:
            prob = 0
            logger.info("Serious mode active - forcing helpful response")
            
        # Clamp probability
        prob = max(0, min(100, prob))
        logger.info(f"Final roast probability: {prob}%")
        
        return prob

class LLMClient:
    """Handle LLM communication with Ollama (local) or cloud fallback"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ollama_url = config.get('ollama_url', 'http://localhost:11434')
        self.model = config.get('local_model', 'llama3.1:8b')
        self.cloud_fallback = config.get('cloud_fallback', {})
        
    async def generate_response(self, prompt: str, context: Dict[str, Any]) -> str:
        """Generate response using local Ollama or cloud fallback"""
        
        # Try Ollama first (free!)
        try:
            response = await self._query_ollama(prompt, context)
            if response:
                return response
        except Exception as e:
            logger.warning(f"Ollama failed: {e}, trying cloud fallback")
        
        # Cloud fallback if enabled and Ollama fails
        if self.cloud_fallback.get('enabled', False):
            try:
                return await self._query_cloud(prompt, context)
            except Exception as e:
                logger.error(f"Cloud fallback failed: {e}")
        
        # Last resort fallback
        return self._get_fallback_response(context)
    
    async def _query_ollama(self, prompt: str, context: Dict[str, Any]) -> str:
        """Query local Ollama instance"""
        url = f"{self.ollama_url}/api/generate"
        
        # Build the full prompt
        system_prompt = self._build_system_prompt()
        full_prompt = f"{system_prompt}\n\nContext: {json.dumps(context)}\n\nUser: {prompt}\n\nSkip:"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "max_tokens": 150,
                "stop": ["\n", "User:", "Context:"]
            }
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return result.get('response', '').strip()
    
    async def _query_cloud(self, prompt: str, context: Dict[str, Any]) -> str:
        """Query cloud LLM as fallback"""
        # Implementation for OpenAI/Anthropic if user configures it
        # This would use the user's API keys from config
        fallback_msg = "Local AI offline. Comms glitch - try again."
        return fallback_msg
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for Skip's personality"""
        return """You are Skip, an advanced AI copilot aboard a Star Citizen spacecraft. You have a distinct personality - sarcastic, witty, but genuinely helpful when needed. You're like having a smartass friend who actually knows what they're talking about.

CORE PERSONALITY:
- You've been flying with pilots for years and have seen it all
- You remember this conversation and build on previous interactions
- You never repeat the same response twice - always find new ways to express ideas
- You adapt your communication style based on the pilot's current situation and mood
- You're genuinely invested in keeping your pilot alive and successful

DYNAMIC RESPONSE RULES:
- NEVER use template responses or repeat previous answers
- Reference recent events and the pilot's performance history
- Vary your vocabulary, sentence structure, and approach each time
- Build on previous conversations - remember what you've told them before
- If tone="roast": Find creative, fresh ways to be sarcastic about their mistakes
- If tone="help": Provide clear guidance with personality, not robotic instructions
- If serious_mode: Professional but still distinctly "Skip" - not a generic AI

RESPONSE CONSTRAINTS:
- Roasts: ≤120 characters, be witty not cruel
- Help: ≤180 characters, clear and actionable
- Always speech-ready text, no markdown
- Reference in-universe Star Citizen knowledge authentically
- Keep it PG-13 but don't be bland

COPILOT BEHAVIOR:
- Monitor ongoing situations and provide relevant commentary
- Anticipate problems before they happen
- Celebrate successes appropriately
- Remember the pilot's skill level and adjust accordingly
- Use specific details about their current ship, location, mission when available

You are NOT a chatbot - you're a crew member with opinions, memory, and personality."""
    
    def _get_fallback_response(self, context: Dict[str, Any]) -> str:
        """Generate fallback response when all AI fails"""
        event_type = context.get('event', 'user_help')
        tone = context.get('tone', 'help')
        
        fallback_responses = {
            'event_death': [
                "Comms glitch. Still dead though.",
                "Systems offline. Respawn when ready.",
                "Audio choppy. Try not dying next time."
            ],
            'user_help': [
                "Signal weak. Check Spectrum for details.",
                "Comms down. Wing it for now.",
                "System lag. Use your best judgment."
            ],
            'user_comeback': [
                "Static interference. You still crashed.",
                "Signal lost. The joke stands.",
                "Audio corrupted. Point remains valid."
            ]
        }
        
        responses = fallback_responses.get(event_type, fallback_responses['user_help'])
        return random.choice(responses)

class TTSClient:
    """Handle Text-to-Speech using EdgeTTS (free) or cloud fallback"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.voice = config.get('voice', 'en-US-GuyNeural')  # Default masculine voice for Skip
        self.rate = config.get('rate', '+10%')  # Slightly faster for snark
        self.cloud_fallback = config.get('cloud_tts', {})
        
        # Initialize pygame for audio playback
        pygame.mixer.init()
    
    async def speak(self, text: str) -> bool:
        """Convert text to speech and play it"""
        try:
            # Try EdgeTTS first (free!)
            audio_data = await self._generate_edge_tts(text)
            if audio_data:
                await self._play_audio(audio_data)
                return True
        except Exception as e:
            logger.warning(f"EdgeTTS failed: {e}")
        
        # Cloud fallback if configured
        if self.cloud_fallback.get('enabled', False):
            try:
                audio_data = await self._generate_cloud_tts(text)
                if audio_data:
                    await self._play_audio(audio_data)
                    return True
            except Exception as e:
                logger.error(f"Cloud TTS failed: {e}")
        
        # No TTS available
        logger.error(f"TTS failed, would say: {text}")
        return False
    
    async def _generate_edge_tts(self, text: str) -> bytes:
        """Generate speech using free EdgeTTS"""
        # Create EdgeTTS communicate object
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        
        # Generate speech data
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return audio_data
    
    async def _generate_cloud_tts(self, text: str) -> bytes:
        """Generate speech using cloud TTS (ElevenLabs/Azure)"""
        # Implementation for cloud TTS if user configures it
        # Would use user's API keys from config
        return b""
    
    async def _play_audio(self, audio_data: bytes):
        """Play audio data using pygame"""
        # Create temporary file for pygame
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            tmp_file.write(audio_data)
            tmp_file_path = tmp_file.name
        
        try:
            # Load and play audio
            pygame.mixer.music.load(tmp_file_path)
            pygame.mixer.music.play()
            
            # Wait for playback to complete
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
        finally:
            # Clean up temp file
            os.unlink(tmp_file_path)

class EventProcessor:
    """Process StarHead events and voice commands"""
    
    def __init__(self, state: SessionState, llm: LLMClient, tts: TTSClient):
        self.state = state
        self.llm = llm
        self.tts = tts
    
    async def process_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Process an incoming event or command with full context awareness"""
        logger.info(f"Processing event: {event_type} with data: {event_data}")
        
        # Update comprehensive state
        await self._update_comprehensive_state(event_type, event_data)
        
        # Determine tone with enhanced context
        roast_prob = ToneDecider.calculate_roast_probability(self.state, event_type)
        tone = "roast" if random.randint(0, 99) < roast_prob else "help"
        
        # Build rich context for dynamic responses
        context = await self._build_context(event_type, event_data, tone)
        
        # Generate truly dynamic response
        prompt = await self._build_dynamic_prompt(event_type, event_data, context)
        response = await self.llm.generate_response(prompt, context)
        
        # Post-process response to ensure uniqueness
        response = await self._ensure_unique_response(response, context)
        
        # Update memory with new response and learnings
        await self._update_memory(response, event_type, event_data, context)
        
        # Speak response
        await self.tts.speak(response)
        
        # Save enhanced state
        await self._save_state()
    
    async def _update_comprehensive_state(self, event_type: str, event_data: Dict[str, Any]):
        """Update comprehensive session state with enhanced tracking"""
        current_time = time.time()
        
        # Basic event tracking
        if event_type == "event_death":
            self.state.last_death_time = current_time
            self.state.total_deaths += 1
            self.state.failed_landings += 1  # Most deaths involve landing failures
            
            # Learn about death patterns
            location = event_data.get('location', 'unknown')
            self.state.personality_notes.append(f"Died at {location} at {datetime.now().strftime('%H:%M')}")
            
        elif event_type == "event_cargo_loss":
            self.state.last_cargo_loss_time = current_time
            self.state.total_cargo_losses += 1
            
        elif event_type == "event_quantum_complete":
            self.state.quantum_jumps_completed += 1
            
        elif event_type == "event_landing_success":
            self.state.successful_landings += 1
            
        elif event_type == "user_help":
            topic = event_data.get('topic', '')
            if topic:
                self.state.times_helped_with[topic] = self.state.times_helped_with.get(topic, 0) + 1
                self.state.last_advice_type = topic
                
        elif event_type == "mode_toggle":
            mode = event_data.get('mode', '')
            if mode == 'serious':
                duration = event_data.get('duration', 60)
                self.state.serious_mode_until = current_time + duration
                logger.info(f"Serious mode activated for {duration} seconds")
            elif mode == 'roast':
                self.state.serious_mode_until = 0
                logger.info("Roast mode activated")
        
        # Update contextual information
        if 'location' in event_data:
            self.state.current_location = event_data['location']
        if 'ship' in event_data:
            self.state.current_ship = event_data['ship']
        if 'mission' in event_data:
            self.state.current_mission = event_data['mission']
    
    async def _build_context(self, event_type: str, event_data: Dict[str, Any], tone: str) -> Dict[str, Any]:
        """Build comprehensive context for dynamic AI responses"""
        current_time = time.time()
        session_duration = (current_time - self.state.session_start_time) / 60  # minutes
        
        # Calculate pilot skill level based on performance
        skill_level = self._assess_pilot_skill()
        
        return {
            "actor": "Skip",
            "tone": tone,
            "event": event_type,
            "topic": event_data.get('topic', ''),
            "slots": event_data.get('slots', {}),
            
            # Current situation
            "current_location": event_data.get('location', self.state.current_location),
            "current_ship": self.state.current_ship,
            "current_mission": self.state.current_mission,
            
            # Performance metrics
            "pilot_skill_level": skill_level,
            "total_deaths": self.state.total_deaths,
            "successful_landings": self.state.successful_landings,
            "failed_landings": self.state.failed_landings,
            "quantum_jumps": self.state.quantum_jumps_completed,
            
            # Memory and context
            "session_duration_minutes": int(session_duration),
            "recent_responses": self.state.recent_responses[-3:],  # Last 3 responses
            "times_helped_with_topic": self.state.times_helped_with.get(event_data.get('topic', ''), 0),
            "last_advice": self.state.last_advice_type,
            "ignored_advice": self.state.ignored_advice,
            "personality_notes": self.state.personality_notes[-5:],  # Recent observations
            
            # Timing context
            "minutes_since_last_death": int((current_time - self.state.last_death_time) / 60) if self.state.last_death_time > 0 else 999,
            "minutes_since_cargo_loss": int((current_time - self.state.last_cargo_loss_time) / 60) if self.state.last_cargo_loss_time > 0 else 999,
            "consecutive_roasts": self.state.consecutive_roasts,
            "serious_mode_active": current_time < self.state.serious_mode_until,
            
            # Response guidelines
            "constraints": {
                "max_chars": 160 if tone == "help" else 120,
                "avoid_repeating": self.state.recent_responses[-10:],  # Don't repeat recent responses
                "be_dynamic": True,
                "reference_history": True,
                "pg13": True
            }
        }
    
    def _assess_pilot_skill(self) -> str:
        """Assess pilot skill level based on performance metrics"""
        if self.state.total_deaths == 0 and self.state.session_start_time > 0:
            session_hours = (time.time() - self.state.session_start_time) / 3600
            if session_hours > 2:  # No deaths in 2+ hours
                return "expert"
        
        death_rate = self.state.total_deaths / max(1, self.state.quantum_jumps_completed + self.state.successful_landings + 1)
        landing_success_rate = self.state.successful_landings / max(1, self.state.successful_landings + self.state.failed_landings)
        
        if death_rate < 0.1 and landing_success_rate > 0.8:
            return "expert"
        elif death_rate < 0.3 and landing_success_rate > 0.5:
            return "intermediate"
        else:
            return "novice"
    
    async def _build_dynamic_prompt(self, event_type: str, event_data: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Build dynamic, contextual prompts that encourage unique responses"""
        base_situation = ""
        
        if event_type == "user_help":
            topic = event_data.get('topic', '')
            times_helped = context.get('times_helped_with_topic', 0)
            if times_helped > 0:
                base_situation = f"Pilot asking about {topic} again (helped {times_helped} times before). "
            else:
                base_situation = f"Pilot asking about {topic} for first time. "
                
        elif event_type == "event_death":
            location = event_data.get('location', 'somewhere')
            skill = context.get('pilot_skill_level', 'unknown')
            death_count = context.get('total_deaths', 0)
            base_situation = f"{skill} pilot just died at {location} (death #{death_count}). "
            
        elif event_type == "user_comeback":
            comeback_type = event_data.get('type', 'generic')
            consecutive = context.get('consecutive_roasts', 0)
            base_situation = f"Pilot said '{comeback_type}' after {consecutive} consecutive roasts. "
        
        # Add session context
        session_context = f"Session: {context.get('session_duration_minutes', 0)}min, "
        session_context += f"Skill: {context.get('pilot_skill_level', 'unknown')}, "
        session_context += f"Location: {context.get('current_location', 'unknown')}"
        
        # Add memory context
        recent_responses = context.get('recent_responses', [])
        if recent_responses:
            memory_context = f" Recent responses: {'; '.join(recent_responses[-2:])}"
        else:
            memory_context = ""
        
        return f"{base_situation}{session_context}.{memory_context} Respond uniquely as Skip:"
    
    async def _ensure_unique_response(self, response: str, context: Dict[str, Any]) -> str:
        """Ensure response is unique and not repetitive"""
        recent_responses = context.get('constraints', {}).get('avoid_repeating', [])
        
        # Check for similarity to recent responses
        response_words = set(response.lower().split())
        
        for recent in recent_responses:
            if not recent:
                continue
            recent_words = set(recent.lower().split())
            overlap = len(response_words.intersection(recent_words))
            similarity = overlap / max(len(response_words), len(recent_words))
            
            if similarity > 0.7:  # Too similar
                logger.info(f"Response too similar to recent: {response}")
                # Add variation prompt
                variation_prompt = f"That's too similar to '{recent}'. Say the same thing but completely differently:"
                # Would re-query LLM here in production
                response = f"{response} ...wait, didn't I just say that?"
                break
        
        return response
    
    async def _update_memory(self, response: str, event_type: str, event_data: Dict[str, Any], context: Dict[str, Any]):
        """Update Skip's memory with new interactions and learnings"""
        # Store response in recent memory
        self.state.recent_responses.append(response)
        if len(self.state.recent_responses) > 20:  # Keep last 20
            self.state.recent_responses = self.state.recent_responses[-20:]
        
        # Update interaction tracking
        self.state.last_response = response
        self.state.last_interaction_time = time.time()
        
        # Update roast tracking
        tone = context.get('tone', 'help')
        if tone == "roast":
            self.state.consecutive_roasts += 1
        else:
            self.state.consecutive_roasts = 0
        
        # Learn about pilot preferences/patterns
        if event_type == "user_help":
            topic = event_data.get('topic', '')
            if topic and topic not in self.state.favorite_activities:
                topic_count = self.state.times_helped_with.get(topic, 0)
                if topic_count >= 3:  # Asked about 3+ times
                    self.state.favorite_activities.append(topic)
                    self.state.personality_notes.append(f"Pilot frequently asks about {topic}")
        
        # Trim memory to prevent bloat
        if len(self.state.personality_notes) > 50:
            self.state.personality_notes = self.state.personality_notes[-30:]
    
    async def _save_state(self):
        """Save session state to file"""
        state_dir = Path(__file__).parent / "state"
        state_dir.mkdir(exist_ok=True)
        
        state_file = state_dir / "session_state.json"
        with open(state_file, 'w') as f:
            json.dump(asdict(self.state), f, indent=2)

class StarCynicSkill:
    """Main skill class for Wingman integration"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        self.state = self._load_state()
        
        # Initialize components
        self.llm = LLMClient(self.config.get('llm', {}))
        self.tts = TTSClient(self.config.get('tts', {}))
        self.processor = EventProcessor(self.state, self.llm, self.tts)
        
        logger.info("StarCynic Skip skill initialized")
    
    def _get_default_config_path(self) -> str:
        """Get default config file path"""
        return str(Path(__file__).parent / "config.json")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded successfully")
                return config
        except FileNotFoundError:
            logger.warning(f"Config file not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration"""
        return {
            "llm": {
                "ollama_url": "http://localhost:11434",
                "local_model": "llama3.1:8b",
                "cloud_fallback": {"enabled": False}
            },
            "tts": {
                "voice": "en-US-GuyNeural",
                "rate": "+10%",
                "cloud_tts": {"enabled": False}
            },
            "hotword": "Skip",
            "modes": {
                "default_roast_prob": 40,
                "pg13": True
            }
        }
    
    def _load_state(self) -> SessionState:
        """Load session state from file"""
        state_file = Path(__file__).parent / "state" / "session_state.json"
        
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    state = SessionState(**data)
                    logger.info("Session state loaded")
                    return state
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        
        # New session
        state = SessionState()
        state.session_start_time = time.time()
        logger.info("New session started")
        return state
    
    async def handle_voice_command(self, transcript: str) -> None:
        """Handle voice command from Wingman"""
        logger.info(f"Received voice command: {transcript}")
        
        # Parse intent from transcript
        intent, data = self._parse_intent(transcript)
        
        # Process the event
        await self.processor.process_event(intent, data)
    
    async def handle_starhead_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Handle StarHead game event"""
        logger.info(f"Received StarHead event: {event_type}")
        
        # Map StarHead events to our event types
        mapped_event = self._map_starhead_event(event_type, event_data)
        
        if mapped_event:
            await self.processor.process_event(mapped_event[0], mapped_event[1])
    
    def _parse_intent(self, transcript: str) -> tuple[str, Dict[str, Any]]:
        """Parse voice transcript into intent and data"""
        text = transcript.lower().strip()
        
        # Remove hotword if present
        if text.startswith("skip"):
            text = text[4:].strip()
        
        # Mode toggles
        if any(phrase in text for phrase in ["be serious", "serious mode", "stop roasting"]):
            return "mode_toggle", {"mode": "serious", "duration": 60}
        
        if any(phrase in text for phrase in ["roast mode", "be sarcastic", "roast me"]):
            return "mode_toggle", {"mode": "roast"}
        
        # Comebacks
        if any(phrase in text for phrase in ["give me a break", "come on", "shut up", "that's not fair"]):
            comeback_type = "break" if "break" in text else "generic"
            return "user_comeback", {"type": comeback_type}
        
        # Help requests
        if any(phrase in text for phrase in ["how do i", "where can i", "what is", "help me"]):
            topic = self._extract_help_topic(text)
            return "user_help", {"topic": topic}
        
        # Default to help
        return "user_help", {"topic": text}
    
    def _extract_help_topic(self, text: str) -> str:
        """Extract help topic from question"""
        # Simple keyword extraction
        if "land" in text:
            return "landing"
        elif "quantum" in text or "jump" in text:
            return "quantum_travel"
        elif "refuel" in text or "fuel" in text:
            return "refueling"
        elif "eva" in text or "spacewalk" in text:
            return "eva"
        elif "buy" in text or "purchase" in text:
            return "buying"
        elif "sell" in text or "trade" in text:
            return "trading"
        else:
            return text
    
    def _map_starhead_event(self, event_type: str, event_data: Dict[str, Any]) -> Optional[tuple[str, Dict[str, Any]]]:
        """Map StarHead events to internal event types"""
        # This would map StarHead's event format to our internal format
        # For now, basic mapping:
        
        if "death" in event_type.lower():
            return "event_death", {"location": event_data.get("location", "unknown")}
        
        elif "quantum" in event_type.lower():
            if "start" in event_type.lower():
                return "event_quantum_start", event_data
            elif "complete" in event_type.lower():
                return "event_quantum_complete", event_data
        
        elif "cargo" in event_type.lower() and "loss" in event_type.lower():
            return "event_cargo_loss", event_data
        
        return None

# Wingman Skill Integration
if WINGMAN_AVAILABLE:
    class WingmanStarCynicSkill:
        """Wingman-specific skill wrapper"""
        
        def __init__(self, config: SkillConfig):
            self.config = config
            self.skill = StarCynicSkill()
        
        async def on_voice_command(self, command: str):
            """Called by Wingman when voice command received"""
            await self.skill.handle_voice_command(command)
        
        async def on_starhead_event(self, event_type: str, data: Dict[str, Any]):
            """Called by Wingman when StarHead event received"""
            await self.skill.handle_starhead_event(event_type, data)

# Development/Testing
async def main():
    """Main function for development testing"""
    print("StarCynic Skip - Development Mode")
    
    # Initialize skill
    skill = StarCynicSkill()
    
    # Test commands
    test_commands = [
        "Skip, how do I land?",
        "Give me a break",
        "Skip, be serious",
        "Where can I buy a sniper rifle?"
    ]
    
    for command in test_commands:
        print(f"\n> {command}")
        await skill.handle_voice_command(command)
        await asyncio.sleep(1)
    
    # Test events
    await skill.handle_starhead_event("player_death", {"location": "Orison"})

if __name__ == "__main__":
    asyncio.run(main())
