"""Load training planning prompts from the agent prompt directory."""
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent / 'prompts'


def planning_settings():
    return {
        'default_principles': (PROMPTS / 'training_principles.md').read_text(encoding='utf-8'),
        'guidance_prompt': (PROMPTS / 'training_plan.md').read_text(encoding='utf-8'),
    }
