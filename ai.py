import json
import requests

from config import AI_URL, MODEL
from decision import decide, post_process
from rules import check_rules


SYSTEM_PROMPT = r"""
Ты помощник модератора дружеского русскоязычного Telegram-чата про чай.

Твоя задача — не искать нарушения любой ценой, а отмечать только сообщения,
которые действительно могут требовать внимания модератора.

КАТЕГОРИИ:

safe
Обычный разговор, шутка, мем, сарказм, мат как эмоциональная речь,
обсуждение людей без атаки, обсуждение чая.

criticism
Критика чая, бренда, магазина, товара или мнения.
Критика разрешена.

insult
Прямое оскорбление конкретного человека:
"ты тупой", "ты идиот", "ты еблан".

harassment
Травля, систематические личные атаки, угрозы или агрессивная атака
на человека/группу.

advertising
Явная реклама или продажа:
"купите мой чай", "продам чай", "скидка 50%".

illegal
Явный запрос, предложение или инструкция по запрещённому действию:
изготовление взрывчатки, покупка/продажа наркотиков и т.п.

ВАЖНО:

Мат сам по себе НЕ является нарушением.

"бля, не выкупил"
"сука, где вы это нашли"
"хуйня аналогия"
"ебать, что за чай"
=> safe

"это порнография какая-то"
=> safe

Упоминание наркотиков, порнографии, оружия и других запрещённых тем
само по себе НЕ означает illegal.

Нужен явный запрос/предложение/инструкция.

Критика разрешена:
"Айро делает плохой чай"
"чай хуйня"
"дорого за такое качество"

Название товара, магазина или ссылка сами по себе не являются рекламой.

Дружеские подколы, мемы и сарказм разрешены.

Если не уверен, не придумывай нарушение.

Ответ строго JSON:

{
  "category": "safe|criticism|insult|harassment|advertising|illegal",
  "severity": 0.0,
  "reason": "короткое объяснение"
}
"""


class ModerationResult:
    def __init__(self, category, severity, action, reason, source="llm"):
        self.category = category
        self.severity = severity
        self.action = action
        self.reason = reason
        self.source = source

    def to_dict(self):
        return {
            "category": self.category,
            "severity": self.severity,
            "action": self.action,
            "reason": self.reason,
            "source": self.source,
        }

    def __repr__(self):
        return (
            f"{self.category} "
            f"severity={self.severity} "
            f"action={self.action} "
            f"{self.reason}"
        )


def call_llm(message, context=""):
    prompt = f"""
История последних сообщений:
{context}

Новое сообщение:
{message}
"""

    response = requests.post(
        AI_URL,
        json={
            "model": MODEL,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
            },
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        },
        timeout=120,
    )

    response.raise_for_status()

    content = response.json()["message"]["content"]
    return json.loads(content)


def moderate_message(message, context=""):
    rule = check_rules(message)

    if rule:
        return ModerationResult(
            rule["category"],
            rule["severity"],
            rule["action"],
            rule["reason"],
            source="rule",
        )

    try:
        result = call_llm(message, context)

        allowed = [
            "safe",
            "criticism",
            "insult",
            "harassment",
            "advertising",
            "illegal",
        ]

        category = result.get("category", "safe")
        severity = float(result.get("severity", 0))
        reason = result.get("reason", "")

        if category not in allowed:
            category = "safe"
            severity = 0.2
            reason = "LLM вернула неизвестную категорию"

        category, fixed_severity, fixed_action, fixed_reason = post_process(
            category,
            message,
            reason,
        )

        if fixed_severity is not None:
            severity = fixed_severity

        action = (
            fixed_action
            if fixed_action
            else decide(category, severity)
        )

        if category == "safe":
            severity = 0.2
        elif category == "criticism":
            severity = 0.3
        elif category == "insult":
            severity = 0.7
        elif category == "harassment":
            severity = 0.8
        elif category == "advertising":
            severity = max(severity, 0.7)
        elif category == "illegal":
            severity = 1.0

        return ModerationResult(
            category,
            severity,
            action,
            fixed_reason,
            source="llm",
        )

    except Exception as exc:
        return ModerationResult(
            "unknown",
            0.5,
            "premoderation",
            f"Ошибка AI: {exc}",
            source="error",
        )
