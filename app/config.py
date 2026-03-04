from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str

    # Hamsa is used for both STT and TTS — single API key

    # Hamsa TTS (tryhamsa.com)
    hamsa_api_key: str
    hamsa_voice_id: str

    # MongoDB
    mongodb_uri: str
    mongodb_database: str = "voice_agent"

    # Application
    app_base_url: str
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ChromaDB
    chroma_host: str = "chromadb"
    chroma_port: int = 8001

    # RAG
    embedding_model: str = "intfloat/multilingual-e5-large"
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Concurrency
    max_concurrent_calls: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
