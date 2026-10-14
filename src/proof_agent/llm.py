"""Client LLM unifié (Groq, Gemini, OpenAI, Ollama) + deux fournisseurs sans réseau.

- « baseline » : PAS un LLM. Propose toujours la même tactique automatique
  (`intros; simpl; auto.`, puis `intros; lia.`). Sert de point de comparaison :
  un agent LLM n'a d'intérêt que s'il fait mieux que cette automatisation naïve.
- « scripted » : réponses fixées à l'avance, pour les tests unitaires.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

from dotenv import load_dotenv

load_dotenv()


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """Quota du fournisseur épuisé pour longtemps (ex. limite de tokens par jour)."""


_WAIT = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.I)


def parse_wait_seconds(message: str) -> float | None:
    """Extrait « try again in 3m51.1s » -> 231.1 secondes."""
    m = _WAIT.search(message)
    if not m or not any(m.groups()):
        return None
    h, mn, s = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mn * 60 + s


DEFAULT_MODELS = {
    "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "gemini": os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "ollama": os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    "baseline": "intros;simpl;auto",
    "scripted": "scripted",
}


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None,
                 temperature: float = 0.2):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "baseline")).lower()
        if self.provider not in DEFAULT_MODELS:
            raise LLMError(f"Fournisseur inconnu : {self.provider}")
        self.model = model or DEFAULT_MODELS[self.provider]
        self.temperature = temperature
        self.calls = 0
        self.tokens = 0          # tokens consommés (si le fournisseur les renvoie)
        self.max_wait = float(os.getenv("LLM_MAX_WAIT_SECONDS", "90"))
        # Pour les modèles qui raisonnent (gpt-oss) : low | medium | high.
        # « low » consomme beaucoup moins de tokens (utile avec un quota gratuit).
        self.reasoning_effort = os.getenv("GROQ_REASONING_EFFORT") or None
        self._script: list[str] = []

    def set_script(self, answers: list[str]) -> None:
        """Pour le fournisseur « scripted » : réponses successives à renvoyer."""
        self._script = list(answers)

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return getattr(self, f"_{self.provider}")(system, user)

    # ------------------------------------------------------------------ #
    def _baseline(self, system: str, user: str) -> str:
        # 1re tentative : automatisation générique ; ensuite : arithmétique.
        if "tentative précédente" in user:
            return "```coq\nintros; lia.\n```"
        return "```coq\nintros; simpl; auto.\n```"

    def _scripted(self, system: str, user: str) -> str:
        if not self._script:
            raise LLMError("Plus de réponse scriptée disponible.")
        return self._script.pop(0)

    def _chat_openai_compatible(self, client, system: str, user: str,
                                extra: dict | None = None) -> str:
        """Appel compatible OpenAI, avec gestion des limites de débit.

        - limite courte (par minute) : on attend le délai indiqué et on réessaie ;
        - limite longue (par jour, ou attente > max_wait) : QuotaExhausted, pour
          que l'évaluation s'arrête proprement en gardant ses résultats.
        """
        for attempt in range(6):
            try:
                r = client.chat.completions.create(
                    model=self.model, temperature=self.temperature,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    **(extra or {}))
                usage = getattr(r, "usage", None)
                if usage is not None and getattr(usage, "total_tokens", None):
                    self.tokens += usage.total_tokens
                return r.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001 — SDK différents, même logique
                msg = str(e)
                if "429" not in msg and "rate limit" not in msg.lower():
                    raise
                wait = parse_wait_seconds(msg)
                per_day = "per day" in msg.lower() or "(TPD)" in msg or "(RPD)" in msg
                if per_day or (wait is not None and wait > self.max_wait):
                    raise QuotaExhausted(msg) from e
                time.sleep((wait or 10 * (attempt + 1)) + 1)
        raise QuotaExhausted("Limite de débit persistante après plusieurs essais.")

    def _groq(self, system: str, user: str) -> str:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY manquante dans .env")
        extra = ({"reasoning_effort": self.reasoning_effort}
                 if self.reasoning_effort else None)
        # max_retries=0 : c'est nous qui gérons les attentes (voir ci-dessus).
        return self._chat_openai_compatible(
            Groq(api_key=key, max_retries=0), system, user, extra)

    def _openai(self, system: str, user: str) -> str:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise LLMError("OPENAI_API_KEY manquante dans .env")
        return self._chat_openai_compatible(OpenAI(api_key=key), system, user)

    def _gemini(self, system: str, user: str) -> str:
        import google.generativeai as genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY manquante dans .env")
        genai.configure(api_key=key)
        m = genai.GenerativeModel(self.model, system_instruction=system)
        return m.generate_content(
            user, generation_config={"temperature": self.temperature}).text or ""

    def _ollama(self, system: str, user: str) -> str:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        payload = json.dumps({"model": self.model, "system": system,
                              "prompt": user, "stream": False,
                              "options": {"temperature": self.temperature}}).encode()
        req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read()).get("response", "")
