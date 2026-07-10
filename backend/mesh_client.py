"""
Shared Mesh API client setup. Both main.py and interview_routes.py import
from here, so the OpenAI-compatible client is configured exactly once.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MESH_API_KEY = os.getenv("MESH_API_KEY")
if not MESH_API_KEY or MESH_API_KEY == "mesh_sk_your_key_here":
    raise RuntimeError(
        "MESH_API_KEY is not set. Create a .env file in this folder with your real key."
    )

client = OpenAI(
    base_url="https://api.meshapi.ai/v1",
    api_key=MESH_API_KEY,
)

HAIKU = "anthropic/claude-haiku-4.5"
SONNET = "anthropic/claude-sonnet-4.6"
