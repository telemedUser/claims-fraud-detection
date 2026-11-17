"""Checks that GEMINI_API_KEY in .env works. Usage: python scripts/check_llm_key.py"""
import httpx

key = open(".env").read().split("=", 1)[1].strip()
body = {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}]}
endpoints = {
    "vertex-express": "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash:generateContent",
    "gemini-api": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
}
for name, url in endpoints.items():
    r = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=60)
    print(name, r.status_code, r.text[:250].replace("\n", " "))
