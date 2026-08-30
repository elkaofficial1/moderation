# AI Telegram Moderator

AI-помощник модератора Telegram-чата.

## Возможности

- анализ сообщений через Ollama;
- контекст последних сообщений;
- safe / criticism / insult / harassment / advertising / illegal;
- observe mode;
- тикеты модератору;
- inline-действия;
- SQLite;
- бан и разбан;
- статистика;
- Docker Compose.

## Режим observe

OBSERVE_MODE=true

Бот ничего не удаляет и никого не банит.

## Active

OBSERVE_MODE=false

Автоматически блокируются только очевидные illegal-сценарии при AUTO_BAN=true.

Оскорбления, harassment и реклама автоматически не банятся.

## Запуск

docker compose up -d --build

## Логи

docker compose logs -f

## Команды

/status
/stats
/tickets
/ticket ID
/ban USER_ID причина
/unban USER_ID
/help
