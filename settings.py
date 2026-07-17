import os
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings with env variable support and validation"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    AGENT_TRIGGER: bool = Field(default=True, description="Agent First communication")


    ENVIRONMENT: str = Field(default="development", description="Environment to run the application in")

    # SPEECH-TO-TEXT SETTINGS
    DEEPGRAM_API_KEY: Optional[str] = Field(default=None, description="Deepgram API key for STT service")


    # LLM SETTINGS FOR AGENT
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key for LLM access")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Gemini API key for LLM access")
    LLM_MODEL_NAME: str = Field(default="gpt-4.1", description="LLM model name to use")

    # MongoDB Database
    DATABASE_HOST: str = Field(default="mongodb://localhost:27017", description="MongoDB connection string")
    DATABASE_NAME: str = Field(default="InfraDB", description="MongoDB database name")
    DATABASE_USERNAME: Optional[str] = Field(default=None, description="MongoDB username")
    DATABASE_PASSWORD: Optional[str] = Field(default=None, description="MongoDB password")
    DATABASE_AUTH_SOURCE: str = Field(default="admin", description="MongoDB authentication database")

    # ELEVENLABS SETTINGS
    ELEVENLABS_API_KEY: Optional[str] = Field(default=None, description="ElevenLabs API key for TTS service")


    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"



settings = Settings()
