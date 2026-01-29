from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargamos .env de forma segura (evita el AssertionError que viste)
load_dotenv(dotenv_path=Path(".") / ".env", override=True)


try:
    from groq import Groq
except Exception:
    Groq = None  # fallback si no esta instalado


def groq_available() -> bool:
    return bool(os.getenv("GROQ_API_KEY")) and Groq is not None


def groq_chat(prompt: str, system: str = "You are a helpful assistant.", temperature: float = 0.2) -> str:
    """
    Llama a Groq Chat Completions.
    Requiere:
      - pip install groq
      - GROQ_API_KEY en .env
    """
    if not groq_available():
        raise RuntimeError("Groq not available. Install `groq` and set GROQ_API_KEY in .env")

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )

    return resp.choices[0].message.content.strip()
