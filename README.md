# hh-bot-v2

Автоматизированный бот для работы с вакансиями и чатами на hh.ru через Playwright и LLM.

Проект умеет:
- собирать вакансии из поисковой выдачи;
- сохранять их в SQLite;
- делать отклик, запонять формы опросов, анкеты, заполнять стандартные поля автоматически;
- использовать LLM для сложных экранов отклика;
- разбирать чаты работодателей и готовить ответы;
- сохранять логи, HTML-снимки и скриншоты для отладки.

## Что внутри

- `bot/collector` — сбор вакансий из выдачи.
- `bot/apply` — логика отклика, работа с формами, submit, prefill salary / cover letter / Telegram.
- `bot/dialogs` — обработка входящих чатов работодателей.
- `bot/llm` — клиент и валидация ответов LLM.
- `bot/db` — SQLite и репозиторий вакансий.
- `config/` — конфиги приложения, профиль кандидата и промпты.

## Зависимости

Основные Python-зависимости: `playwright`, `PyYAML`, `httpx`. Они уже зафиксированы в `requirements.txt` и `pyproject.toml`.

Нужен Python 3.11+ и браузер Chromium для Playwright. Версия проекта и CLI entrypoint также уже описаны в `pyproject.toml`: пакет называется `hh-bot-v2`, а команда запуска — `bot`.
## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp config/config.example.yaml config/config.yaml
cp config/profile.example.yaml config/profile.yaml
```

После этого заполни:
- `config/config.yaml`
- `config/profile.yaml`
- при необходимости `config/prompts.yaml`

## Как запускать браузер

Проект подключается к уже открытому Chromium по CDP URL `http://127.0.0.1:9222`, это значение есть в дефолтной конфигурации загрузчика.

Пример запуска Chromium / Chrome:

```bash
google-chrome   --remote-debugging-port=9222   --user-data-dir=/tmp/hh-bot-profile
```

Либо укажи свой адрес в `config/config.yaml`.

## CLI команды

Команды берутся из `bot/cli/main.py`: `init-db`, `status`, `list`, `run-search`, `run-db`, `run-one`, `dump-form`, `run-dialogs`.

### Инициализация базы

```bash
python -m bot.cli.main init-db
```

### Сбор вакансий из поиска

```bash
python -m bot.cli.main run-search   --urls "https://hh.ru/search/vacancy?text=devops"   --limit 20   --dry-run
```

### Прогон по базе

```bash
python -m bot.cli.main run-db --mode new --limit 10 --dry-run
```

### Один URL

```bash
python -m bot.cli.main run-one   --url "https://hh.ru/vacancy/123456789"   --dry-run
```

### Снять дамп формы

```bash
python -m bot.cli.main dump-form   --url "https://hh.ru/vacancy/123456789"
```

### Обработка диалогов

```bash
python -m bot.cli.main run-dialogs --limit 10 --dry-run
python -m bot.cli.main run-dialogs --chat-id 123456789 --auto
python -m bot.cli.main run-dialogs --chat-url "https://hh.ru/applicant/chats/chat/123456789" --debug-submit
```


## Конфиги

В репозиторий положены безопасные шаблоны:
- `config/config.yaml`
- `config/profile.yaml`
- `config/prompts.yaml`

Личные данные и локальные адреса из исходного дампа я не включал в публичный вариант.

## Ограничения

Проект рассчитан на уже залогиненный hh.ru в браузере, к которому подключается Playwright через CDP. Это не "безголовый" сервис из коробки: сначала нужно поднять браузерную сессию и авторизоваться вручную.
Проект оптимизирован под небольшие ллм, которые помещаются в скромные видеокарты. Тестировался на gtx1060 - 6gb с моделью qwen3:4b-16384ctx. На большинство вызовов ллм уходило до 4000 тысяч токенов и около 30 секунд. Так что можно уменьшить контекст и поместится в 4gb vram. Можно запускать и на цпу (сейчас таймауты стоят 20 минут) если вы готовы долго ждать =)
Скоро буду писать версию под 16гб, которая анализирует текст вакансии и пишет персонализированное сопроводительное письмо.






























































































#0_с
