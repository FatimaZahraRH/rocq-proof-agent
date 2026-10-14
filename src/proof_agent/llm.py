"""Client LLM unifié (Groq, Gemini, OpenAI, Ollama) + deux fournisseurs sans réseau.

- « baseline » : PAS un LLM. Propose toujours la même tactique automatique
  (`intros; simpl; auto.`, puis `intros; lia.`). Sert de point de comparaison :
  un agent LLM n'a d'intérêt que s'il fait mieux que cette automatisation naïve.
- « scripted » : réponses fixées à l'avance, pour les tests unitaires.
"""
from __future__ import annotations

import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv()


class LLMError(RuntimeError):
    pass


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

    def _chat_openai_compatible(self, client, system: str, user: str) -> str:
        r = client.chat.completions.create(
            model=self.model, temperature=self.temperature,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return r.choices[0].message.content or ""

    def _groq(self, system: str, user: str) -> str:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY manquante dans .env")
        return self._chat_openai_compatible(Groq(api_key=key), system, user)

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
