# Блок 4: Дополнительные интеграции (задачи 19, 22)

## Задача 19 — Поиск через Tavily API

### Файлы
- `services/search_service.py` — SearchService, SearchAwareHandler

### Как работает
1. LLM через function calling решает, нужен ли веб-поиск
2. Формулирует поисковый запрос
3. Tavily возвращает top-5 результатов со ссылками
4. Результаты кешируются в Redis на **1 час**
5. LLM формирует финальный ответ с источниками

### Получить API ключ
1. Зарегистрируйтесь: https://app.tavily.com/
2. Скопируйте ключ из Dashboard

### Переменные .env
```dotenv
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxx
```

> Без ключа бот работает без поиска — Groq отвечает из своих знаний.

---

## Задача 22 — Webhook режим

### Файлы
- `webhook_server.py` — альтернативная точка входа вместо `main.py`

### Запуск

**Разработка с ngrok:**
```bash
# Установить ngrok: https://ngrok.com/download
ngrok http 8443

# В .env:
WEBHOOK_HOST=https://xxxx.ngrok.io
WEBHOOK_SECRET=your-secret

# Запуск:
python webhook_server.py
```

**Production с Let's Encrypt:**
```bash
# Получить cert:
certbot certonly --standalone -d yourdomain.com

# В .env:
WEBHOOK_HOST=https://yourdomain.com
SSL_CERT=/etc/letsencrypt/live/yourdomain.com/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/yourdomain.com/privkey.pem

python webhook_server.py
```

**Self-signed сертификат (тест):**
```bash
mkdir ssl
openssl req -newkey rsa:2048 -sha256 -nodes -keyout ssl/key.pem \
    -x509 -days 365 -out ssl/cert.pem -subj "/CN=yourdomain.com"
python webhook_server.py
```

### Переменные .env (webhook)
```dotenv
WEBHOOK_HOST=https://your-domain.com   # URL публичного хоста
WEBHOOK_SECRET=your-secret-token       # Секрет для валидации от Telegram
WEBHOOK_PORT=8443                      # Порт сервера
SSL_CERT=ssl/cert.pem                  # Путь к сертификату (опционально)
SSL_KEY=ssl/key.pem                    # Путь к ключу (опционально)
```

### Polling vs Webhook

| | Polling (`main.py`) | Webhook (`webhook_server.py`) |
|-|---------------------|-------------------------------|
| Latency | ~1-3 сек | ~50ms |
| CPU | постоянные запросы | только при сообщениях |
| Настройка | никакой | нужен публичный HTTPS |
| Graceful shutdown | ✅ | ✅ (дренаж очереди) |

### Health check
```bash
curl http://localhost:8443/health
# OK
```

---

## Новые зависимости Python

Новых пакетов не добавлено (`aiohttp` и `httpx` уже были в requirements.txt).

## Тесты
```bash
pytest tests/test_block4_integrations.py -v
# 10 passed
```
