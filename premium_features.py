#!/usr/bin/env python3
"""
StarCynic Skip - Premium Features Implementation
Modular system for freemium functionality
"""

import json
import requests
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import aiohttp
from datetime import datetime, timedelta
import hashlib

@dataclass
class SubscriptionTier:
    """User subscription information"""
    tier: str = "free"  # free, pro, elite, command
    expires_at: Optional[datetime] = None
    features: List[str] = None
    user_id: str = ""
    org_id: Optional[str] = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = self._get_tier_features()
    
    def _get_tier_features(self) -> List[str]:
        """Get features available for this tier"""
        feature_map = {
            "free": [
                "basic_personality",
                "edge_tts",
                "local_llm",
                "session_memory",
                "basic_roasts",
                "starhead_integration"
            ],
            "pro": [
                "basic_personality", "edge_tts", "local_llm", "session_memory", 
                "basic_roasts", "starhead_integration",
                # Pro additions
                "elevenlabs_tts",
                "custom_personalities",
                "enhanced_memory",
                "performance_analytics",
                "custom_roast_packs",
                "voice_customization"
            ],
            "elite": [
                # All Pro features plus
                "basic_personality", "edge_tts", "local_llm", "session_memory", 
                "basic_roasts", "starhead_integration", "elevenlabs_tts",
                "custom_personalities", "enhanced_memory", "performance_analytics",
                "custom_roast_packs", "voice_customization",
                # Elite additions
                "obs_integration",
                "chat_bot_features",
                "premium_llm_access",
                "streaming_tools",
                "advanced_analytics",
                "multi_session_memory"
            ],
            "command": [
                # All Elite features plus enterprise
                "basic_personality", "edge_tts", "local_llm", "session_memory", 
                "basic_roasts", "starhead_integration", "elevenlabs_tts",
                "custom_personalities", "enhanced_memory", "performance_analytics",
                "custom_roast_packs", "voice_customization", "obs_integration",
                "chat_bot_features", "premium_llm_access", "streaming_tools",
                "advanced_analytics", "multi_session_memory",
                # Command additions
                "white_label",
                "custom_branding",
                "fleet_management",
                "organization_features",
                "api_access",
                "priority_support"
            ]
        }
        return feature_map.get(self.tier, feature_map["free"])
    
    def has_feature(self, feature: str) -> bool:
        """Check if user has access to a feature"""
        if self.tier == "free":
            return feature in self.features
        
        # Check if subscription is active
        if self.expires_at and datetime.now() > self.expires_at:
            return feature in SubscriptionTier("free").features
        
        return feature in self.features

class PremiumFeatureManager:
    """Manages premium feature access and validation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.subscription = SubscriptionTier()
        self.license_server_url = config.get('license_server', 'https://api.starcynic.com')
        self.offline_mode = True  # Start offline, validate async
    
    async def initialize_subscription(self, user_id: str) -> None:
        """Initialize user subscription from license server"""
        try:
            # Try to validate with license server
            subscription_data = await self._validate_subscription(user_id)
            if subscription_data:
                self.subscription = SubscriptionTier(**subscription_data)
                self.offline_mode = False
            else:
                # Fallback to local license file
                local_license = self._load_local_license(user_id)
                if local_license:
                    self.subscription = SubscriptionTier(**local_license)
                
        except Exception as e:
            print(f"License validation failed, using free tier: {e}")
            self.subscription = SubscriptionTier(tier="free")
    
    async def _validate_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Validate subscription with license server"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.license_server_url}/validate",
                    json={"user_id": user_id, "product": "skip"},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('subscription')
        except:
            pass
        return None
    
    def _load_local_license(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Load license from local file (for offline mode)"""
        license_file = Path.home() / ".starcynic" / "license.json"
        
        if license_file.exists():
            try:
                with open(license_file, 'r') as f:
                    license_data = json.load(f)
                    
                # Verify license signature (simple validation)
                if self._verify_license_signature(license_data):
                    return license_data.get('subscription')
            except:
                pass
        return None
    
    def _verify_license_signature(self, license_data: Dict[str, Any]) -> bool:
        """Verify license file hasn't been tampered with"""
        # Simple signature verification (in production, use proper crypto)
        signature = license_data.get('signature', '')
        content = json.dumps(license_data.get('subscription', {}), sort_keys=True)
        expected = hashlib.sha256(f"{content}:skip_secret".encode()).hexdigest()
        return signature == expected
    
    def check_feature_access(self, feature: str) -> bool:
        """Check if current subscription has access to feature"""
        return self.subscription.has_feature(feature)
    
    def get_tier_info(self) -> Dict[str, Any]:
        """Get current subscription tier information"""
        return {
            "tier": self.subscription.tier,
            "expires_at": self.subscription.expires_at.isoformat() if self.subscription.expires_at else None,
            "features": self.subscription.features,
            "offline_mode": self.offline_mode
        }

class PremiumTTSProvider:
    """Enhanced TTS with premium features"""
    
    def __init__(self, config: Dict[str, Any], feature_manager: PremiumFeatureManager):
        self.config = config
        self.feature_manager = feature_manager
        
        # ElevenLabs setup for premium users
        self.elevenlabs_key = config.get('elevenlabs', {}).get('api_key')
        self.custom_voice_id = config.get('elevenlabs', {}).get('voice_id')
        
    async def generate_speech(self, text: str, voice_options: Dict[str, Any] = None) -> bytes:
        """Generate speech with tier-appropriate quality"""
        
        # Premium TTS for Pro+ users
        if self.feature_manager.check_feature_access("elevenlabs_tts") and self.elevenlabs_key:
            return await self._generate_elevenlabs_speech(text, voice_options)
        
        # Fallback to free EdgeTTS
        return await self._generate_edge_speech(text, voice_options)
    
    async def _generate_elevenlabs_speech(self, text: str, voice_options: Dict[str, Any] = None) -> bytes:
        """Generate premium ElevenLabs speech"""
        voice_id = voice_options.get('voice_id', self.custom_voice_id) if voice_options else self.custom_voice_id
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": voice_options.get('stability', 0.5) if voice_options else 0.5,
                "similarity_boost": voice_options.get('similarity', 0.8) if voice_options else 0.8
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                json=data,
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    # Fallback to EdgeTTS on failure
                    return await self._generate_edge_speech(text, voice_options)
    
    async def _generate_edge_speech(self, text: str, voice_options: Dict[str, Any] = None) -> bytes:
        """Generate free EdgeTTS speech"""
        import edge_tts
        
        voice = voice_options.get('voice', 'en-US-GuyNeural') if voice_options else 'en-US-GuyNeural'
        rate = voice_options.get('rate', '+10%') if voice_options else '+10%'
        
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return audio_data

class PremiumPersonalitySystem:
    """Enhanced personality system for premium users"""
    
    def __init__(self, config: Dict[str, Any], feature_manager: PremiumFeatureManager):
        self.config = config
        self.feature_manager = feature_manager
        self.personality_packs = self._load_personality_packs()
    
    def _load_personality_packs(self) -> Dict[str, Dict[str, Any]]:
        """Load available personality packs"""
        packs = {
            "default": {
                "name": "Sarcastic Copilot",
                "description": "Skip's default personality - sarcastic but helpful",
                "system_prompt_additions": "",
                "roast_style": "witty",
                "help_style": "concise"
            }
        }
        
        # Pro+ personality packs
        if self.feature_manager.check_feature_access("custom_personalities"):
            packs.update({
                "military": {
                    "name": "Military ATC",
                    "description": "Professional military air traffic controller",
                    "system_prompt_additions": "You speak like a military air traffic controller. Use proper radio protocols and military terminology.",
                    "roast_style": "disciplined",
                    "help_style": "protocol-focused"
                },
                "british": {
                    "name": "British Butler",
                    "description": "Posh British butler who happens to be a pilot",
                    "system_prompt_additions": "You speak with a proper British accent and butler-like politeness, even when being sarcastic.",
                    "roast_style": "politely_devastating",
                    "help_style": "refined"
                },
                "pirate": {
                    "name": "Space Pirate",
                    "description": "Gruff space pirate with a heart of gold",
                    "system_prompt_additions": "You speak like a space pirate - gruff, with pirate slang, but you're fundamentally helpful.",
                    "roast_style": "rough_affection",
                    "help_style": "practical"
                }
            })
        
        return packs
    
    def get_available_personalities(self) -> List[Dict[str, Any]]:
        """Get list of personalities available to user"""
        available = []
        
        for pack_id, pack in self.personality_packs.items():
            if pack_id == "default" or self.feature_manager.check_feature_access("custom_personalities"):
                available.append({
                    "id": pack_id,
                    "name": pack["name"],
                    "description": pack["description"],
                    "available": True
                })
            else:
                available.append({
                    "id": pack_id,
                    "name": pack["name"],
                    "description": pack["description"],
                    "available": False,
                    "requires": "Skip Pro"
                })
        
        return available
    
    def get_personality_prompt(self, personality_id: str = "default") -> str:
        """Get system prompt for specified personality"""
        if personality_id not in self.personality_packs:
            personality_id = "default"
        
        # Check access
        if personality_id != "default" and not self.feature_manager.check_feature_access("custom_personalities"):
            personality_id = "default"
        
        pack = self.personality_packs[personality_id]
        base_prompt = """You are Skip, an AI copilot for Star Citizen..."""  # Base prompt
        
        additions = pack.get("system_prompt_additions", "")
        if additions:
            return f"{base_prompt}\n\nPersonality Override: {additions}"
        
        return base_prompt

class PremiumAnalytics:
    """Advanced analytics for premium users"""
    
    def __init__(self, config: Dict[str, Any], feature_manager: PremiumFeatureManager):
        self.config = config
        self.feature_manager = feature_manager
        self.analytics_data = {}
    
    def track_interaction(self, event_type: str, context: Dict[str, Any]) -> None:
        """Track interaction for analytics"""
        if not self.feature_manager.check_feature_access("performance_analytics"):
            return
        
        # Track detailed analytics for premium users
        timestamp = datetime.now().isoformat()
        
        self.analytics_data[timestamp] = {
            "event_type": event_type,
            "response_time": context.get("response_time", 0),
            "tone": context.get("tone", "unknown"),
            "pilot_skill": context.get("pilot_skill_level", "unknown"),
            "session_duration": context.get("session_duration_minutes", 0)
        }
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate performance analytics report"""
        if not self.feature_manager.check_feature_access("performance_analytics"):
            return {"error": "Analytics requires Skip Pro"}
        
        # Generate comprehensive report
        return {
            "total_interactions": len(self.analytics_data),
            "avg_response_time": self._calculate_avg_response_time(),
            "tone_distribution": self._calculate_tone_distribution(),
            "skill_progression": self._calculate_skill_progression(),
            "most_common_topics": self._get_common_topics(),
            "performance_trends": self._get_performance_trends()
        }
    
    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time"""
        times = [data.get("response_time", 0) for data in self.analytics_data.values()]
        return sum(times) / len(times) if times else 0
    
    def _calculate_tone_distribution(self) -> Dict[str, int]:
        """Calculate distribution of tones used"""
        tones = {}
        for data in self.analytics_data.values():
            tone = data.get("tone", "unknown")
            tones[tone] = tones.get(tone, 0) + 1
        return tones
    
    def _calculate_skill_progression(self) -> List[Dict[str, Any]]:
        """Track pilot skill progression over time"""
        progression = []
        for timestamp, data in sorted(self.analytics_data.items()):
            progression.append({
                "timestamp": timestamp,
                "skill_level": data.get("pilot_skill", "unknown")
            })
        return progression
    
    def _get_common_topics(self) -> List[Dict[str, Any]]:
        """Get most commonly requested help topics"""
        # Would analyze help requests
        return [
            {"topic": "landing", "count": 15},
            {"topic": "quantum_travel", "count": 8},
            {"topic": "trading", "count": 5}
        ]
    
    def _get_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends"""
        return {
            "response_time_trend": "improving",
            "skill_level_trend": "progressing",
            "engagement_trend": "increasing"
        }

# Integration with main Skip system
class PremiumSkipEnhancer:
    """Enhances base Skip with premium features"""
    
    def __init__(self, base_skip, config: Dict[str, Any]):
        self.base_skip = base_skip
        self.feature_manager = PremiumFeatureManager(config)
        self.premium_tts = PremiumTTSProvider(config, self.feature_manager)
        self.personality_system = PremiumPersonalitySystem(config, self.feature_manager)
        self.analytics = PremiumAnalytics(config, self.feature_manager)
    
    async def initialize(self, user_id: str) -> None:
        """Initialize premium features for user"""
        await self.feature_manager.initialize_subscription(user_id)
    
    async def enhanced_speak(self, text: str, voice_options: Dict[str, Any] = None) -> bool:
        """Enhanced TTS with premium features"""
        audio_data = await self.premium_tts.generate_speech(text, voice_options)
        if audio_data:
            # Play audio using base Skip's audio system
            await self.base_skip.tts._play_audio(audio_data)
            return True
        return False
    
    def get_personality_prompt(self, personality_id: str = "default") -> str:
        """Get enhanced personality prompt"""
        return self.personality_system.get_personality_prompt(personality_id)
    
    def track_interaction(self, event_type: str, context: Dict[str, Any]) -> None:
        """Track interaction for premium analytics"""
        self.analytics.track_interaction(event_type, context)
    
    def get_subscription_status(self) -> Dict[str, Any]:
        """Get current subscription status"""
        return self.feature_manager.get_tier_info()
