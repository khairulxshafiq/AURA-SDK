"""
Centralised LLM calling layer for AURA.
Manages Gemini API key rotation, cooldown tracking, and OpenRouter fallback.
All pipeline modules import from here instead of duplicating key rotation logic.
"""
import os
import logging
import asyncio
import httpx
import threading

from config import GEMINI_KEYS, OPENROUTER_API_KEY, OPENROUTER_FALLBACK_MODEL
import storage.memory_repository as memory

logger = logging.getLogger("aura.pipelines.llm_caller")

# Shared mutable state — all pipelines reference via module access (e.g. llm.current_key_idx)
current_key_idx = 0


async def call_llm(
    prompt: str,
    timeout: float = 6.0,
    openrouter_messages: list = None
) -> str:
    """Unified Gemini + OpenRouter LLM caller with automatic key rotation and cooldown.

    Args:
        prompt: The full prompt text sent to Gemini.
        timeout: Timeout in seconds for each Gemini key attempt.
        openrouter_messages: Explicit message list for OpenRouter fallback.
            If None, defaults to [{"role": "user", "content": prompt}].

    Returns:
        Generated text, or empty string if all attempts fail.
    """
    global current_key_idx

    def _sync_gemini_call(api_key: str) -> str:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text if response and response.text else ""

    num_keys = len(GEMINI_KEYS)
    for attempt in range(num_keys):
        active_key = GEMINI_KEYS[current_key_idx]
        if memory.is_key_on_cooldown(active_key):
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

        os.environ["GEMINI_API_KEY"] = active_key
        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(_sync_gemini_call, active_key),
                timeout=timeout
            )
            if text:
                return text
        except asyncio.TimeoutError:
            logger.warning(f"Gemini key #{current_key_idx + 1} timed out after {timeout}s, placing on cooldown...")
            memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue
        except Exception as err:
            logger.warning(f"Gemini key #{current_key_idx + 1} failed ({err})")
            if "429" in str(err) or "quota" in str(err).lower():
                memory.set_key_cooldown(active_key, 600.0)
            current_key_idx = (current_key_idx + 1) % num_keys
            continue

    # OpenRouter Fallback
    if OPENROUTER_API_KEY:
        try:
            logger.info(f"All Gemini keys in cooldown/failed. Using OpenRouter fallback ({OPENROUTER_FALLBACK_MODEL})...")
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            messages = openrouter_messages or [{"role": "user", "content": prompt}]
            payload = {
                "model": OPENROUTER_FALLBACK_MODEL,
                "messages": messages
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.error(f"OpenRouter error ({r.status_code}): {r.text[:200]}")
        except Exception as or_err:
            logger.error(f"OpenRouter exception: {or_err}")

    return ""


async def call_supervisor_chat_model(agent_message: str, user_id: int = 0) -> str:
    """Direct fast execution for conversational chat with multi-turn history buffer (rolling 48h) and strict 6s timeout."""
    from orchestrator.supervisor import get_supervisor_instructions
    system_instructions = get_supervisor_instructions()

    # Retrieve up to 8 recent chat history messages for conversational context
    history_block = ""
    openrouter_msgs = [{"role": "system", "content": system_instructions}]

    if user_id:
        recent_history = memory.get_recent_chat_history(user_id, limit=8)
        if recent_history:
            history_lines = []
            for h in recent_history:
                role_label = "Pengguna" if h["role"] == "user" else "AURA"
                history_lines.append(f"{role_label}: {h['content']}")
                openrouter_role = "user" if h["role"] == "user" else "assistant"
                openrouter_msgs.append({"role": openrouter_role, "content": h["content"]})
            history_block = "SEJARAH PERBUALAN TERKINI (Konteks Sambungan):\n" + "\n".join(history_lines) + "\n\n"

    openrouter_msgs.append({"role": "user", "content": agent_message})

    prompt = f"{system_instructions}\n\n{history_block}MESEJ PENGGUNA TERBAHARU:\n{agent_message}"

    result = await call_llm(prompt, timeout=6.0, openrouter_messages=openrouter_msgs)
    if not result:
        result = "Ya, AURA di sini! Ada apa-apa yang saya boleh bantu hari ini? ⚡"

    # Save user message and assistant reply to rolling chat history buffer
    if user_id and agent_message:
        try:
            memory.save_chat_message(user_id, "user", agent_message)
            memory.save_chat_message(user_id, "assistant", result)
        except Exception as e:
            logger.warning(f"Could not save chat history: {e}")

    return result



def audit_gemini_keys_async():
    """Non-blocking background check of Gemini API keys to seed 429 cooldown state."""
    def _check():
        for key in GEMINI_KEYS:
            if not memory.is_key_on_cooldown(key):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
                    r = httpx.post(url, json={"contents": [{"parts": [{"text": "ping"}]}]}, timeout=5)
                    if r.status_code == 429:
                        logger.info(f"[KeyAuditor] Gemini key {key[:8]}... returned 429, setting 10-min cooldown.")
                        memory.set_key_cooldown(key, 600.0)
                except Exception as e:
                    logger.warning(f"[KeyAuditor] Key audit ping error for {key[:8]}...: {e}")
    threading.Thread(target=_check, daemon=True).start()
