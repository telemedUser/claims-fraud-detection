"""Calls the configured Gemini model directly and prints status/timing. Usage: python scripts/debug_llm.py [model]"""
import os
import sys
import time

import httpx

from app import llm
from app.settings import get_settings

models = sys.argv[1:] or [llm.gemini_model(), "gemini-flash-latest", "gemini-3.5-flash", "gemini-2.5-flash"]
for m in models:
    t = time.time()
    try:
        r = httpx.post(llm.GEMINI_URL.format(model=m), timeout=45,
                       headers={"x-goog-api-key": get_settings().gemini_api_key.get_secret_value()},
                       json={"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}]})
        print(m, r.status_code, f"{time.time() - t:.1f}s", r.text[:200].replace("\n", " "))
    except Exception as e:
        print(m, type(e).__name__, f"{time.time() - t:.1f}s")
