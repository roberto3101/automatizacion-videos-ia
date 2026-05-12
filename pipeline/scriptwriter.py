"""
Script generation module.
Supports: Claude API (Anthropic), Ollama (free local), or manual input.
"""
import httpx
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")


def _load_settings():
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_prompt(character: dict, topic: str, duration: int, language: str, num_scenes: int) -> str:
    """Build the script generation prompt (shared between all LLM providers)."""
    seconds_per_scene = duration // num_scenes

    sample_hooks = character.get("sample_hooks", [])
    if isinstance(sample_hooks, str):
        try:
            sample_hooks = json.loads(sample_hooks)
        except json.JSONDecodeError:
            sample_hooks = [sample_hooks]

    hooks_text = "\n".join(f"- {h}" for h in sample_hooks[:3]) if sample_hooks else "- Create an original hook"
    lang_instruction = "Write everything in English." if language == "en" else "Write everything in Spanish."

    return f"""You are a viral video scriptwriter. Create a script for a {duration}-second horror/mystery narration video.

CHARACTER:
- Name: {character['name']}
- Personality: {character.get('personality', 'Mysterious storyteller')}
- Visual: {character.get('visual_prompt', 'Old man by campfire')}

TOPIC: {topic}

STYLE HOOKS (use as inspiration):
{hooks_text}

RULES:
1. {lang_instruction}
2. The first 3 seconds MUST hook the viewer — make them NEED to keep watching
3. Create exactly {num_scenes} scenes, each ~{seconds_per_scene} seconds of narration
4. Build tension throughout — the scariest/most shocking part is near the end
5. End with a twist or chilling final line that makes people rewatch
6. Keep narration natural, like someone really telling a story by a fire
7. Use short sentences. Pauses. Let the horror breathe.

VISUAL PROMPT RULES (CRITICAL for AI video consistency):
8. EVERY visual_prompt MUST include the SAME color palette (e.g. "dark blue and amber tones")
9. EVERY visual_prompt MUST include the SAME lighting style (e.g. "warm firelight, deep shadows")
10. EVERY visual_prompt MUST specify camera angle (close-up, medium shot, wide shot)
11. EVERY visual_prompt MUST end with "cinematic, 4K, film grain, shallow depth of field"
12. Use the SAME environment description across scenes (same room, same forest, same location)
13. If the character appears, describe them identically in every scene

Respond ONLY with valid JSON in this exact format:
{{
  "title": "Video title (compelling, clickable, under 60 chars)",
  "hook": "The opening line (first 3 seconds — must grab attention)",
  "scenes": [
    {{
      "scene_number": 1,
      "narration": "What the narrator says in this scene",
      "visual_prompt": "Detailed visual description. MUST include: consistent color palette, lighting, camera angle, setting. End with cinematic quality tags.",
      "duration_seconds": {seconds_per_scene}
    }}
  ]
}}"""


async def generate_script(character: dict, topic: str, duration: int = 60,
                          language: str = "en", context_text: str = "",
                          db = None) -> dict:
    """
    Generate a structured video script using the configured LLM provider.
    Tries in order: Claude API → Ollama (local) → error.

    If a db is provided, production insights are fetched and prepended to the
    prompt so the LLM learns from what's worked in past videos.
    """
    settings = _load_settings()
    num_scenes = min(duration // 10, settings.get("max_scenes", 6))
    prompt = _build_prompt(character, topic, duration, language, num_scenes)

    # Inject production insights from past videos (feedback loop)
    if db is not None:
        try:
            from .analytics import get_production_insights, format_insights_for_prompt
            insights = await get_production_insights(db)
            insight_block = format_insights_for_prompt(insights)
            if insight_block:
                prompt = insight_block + "\n" + prompt
        except Exception as e:
            print(f"[scriptwriter] insights skipped: {e}")

    # Inject explicit context if provided
    if context_text:
        prompt = context_text + "\n\n" + prompt

    # Try Claude API first if key is set
    anthropic_key = settings.get("anthropic_api_key", "")
    if anthropic_key:
        return await _generate_with_claude(prompt, anthropic_key)

    # Try Ollama (free, local)
    ollama_url = settings.get("ollama_url", "http://localhost:11434")
    ollama_model = settings.get("ollama_model", "")
    if ollama_model:
        return await _generate_with_ollama(prompt, ollama_url, ollama_model)

    raise ValueError(
        "No LLM configured. Either:\n"
        "1. Add your Anthropic API key in Settings, OR\n"
        "2. Install Ollama (free) and set ollama_model in settings.json"
    )


async def _generate_with_claude(prompt: str, api_key: str) -> dict:
    """Generate script using Claude API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if response.status_code != 200:
        raise Exception(f"Claude API error ({response.status_code}): {response.text}")

    data = response.json()
    text = data["content"][0]["text"]
    return _parse_script_json(text)


async def _generate_with_ollama(prompt: str, ollama_url: str, model: str) -> dict:
    """
    Generate script using Ollama (free, runs locally).
    Install: https://ollama.ai → ollama pull llama3.2
    Cost: $0. Runs on your GPU/CPU.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.8,
                        "num_predict": 2000,
                    },
                },
            )
        except httpx.ConnectError:
            raise Exception(
                f"Cannot connect to Ollama at {ollama_url}. "
                "Make sure Ollama is running (start it with 'ollama serve')."
            )

    if response.status_code != 200:
        raise Exception(f"Ollama error ({response.status_code}): {response.text}")

    data = response.json()
    text = data.get("response", "")
    return _parse_script_json(text)


def _parse_script_json(text: str) -> dict:
    """Extract and parse JSON from LLM response."""
    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    script = json.loads(text.strip())

    # Validate structure
    if "scenes" not in script:
        raise ValueError("Script missing 'scenes' field")
    if not script["scenes"]:
        raise ValueError("Script has empty scenes list")

    return script
