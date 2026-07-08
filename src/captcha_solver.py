import base64
import json

from openai import OpenAI


def _clean_json(raw: str) -> dict:
    text = (raw or "").replace("```json", "").replace("```", "").strip()
    return json.loads(text)


class CaptchaSolver:
    def __init__(self, openai_api_key=None, on_log=None):
        self.openai_api_key = openai_api_key or ""
        self.on_log = on_log or (lambda msg: None)

    def enabled(self) -> bool:
        return bool(self.openai_api_key)

    def mode(self) -> str:
        return "openai" if self.openai_api_key else "none"

    def solve_publish(self, image_b64: str, prompt: str, hint: str = "") -> dict:
        return self._solve(image_b64, f"{prompt}\n\n힌트 텍스트: {hint}" if hint else prompt)

    def solve_login(self, image_b64: str, prompt: str) -> dict:
        return self._solve(image_b64, prompt)

    def _solve(self, image_b64: str, prompt: str) -> dict:
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API 키가 없습니다.")
        client = OpenAI(api_key=self.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=250,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
        )
        text = response.choices[0].message.content or ""
        return _clean_json(text)