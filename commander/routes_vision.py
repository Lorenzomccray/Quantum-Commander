from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.settings import settings

router = APIRouter()

@router.get("/vision/caption")
def caption(file_id: str, provider: str = "openai", model: str = "gpt-4o-mini", prompt: str = "Describe this image succinctly."):
    if provider != "openai":
        raise HTTPException(400, "Only openai provider supported for vision captioning")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY not configured")
    image_url = f"http://127.0.0.1:8000/files/{file_id}"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        # Use Chat Completions with image content
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        resp = client.chat.completions.create(model=model, messages=msgs)
        text = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "caption": text}
    except Exception as e:
        raise HTTPException(500, f"vision error: {type(e).__name__}: {e}")