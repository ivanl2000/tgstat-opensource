# 📊 tgstat-opensource

**Открытый аналог tgstat.ru** — сбор статистики, аналитика и рейтинг Telegram-каналов.

[![MIT License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)

## 🚀 Возможности

- ✅ **Сбор постов из каналов** через Telethon (User API)
- ✅ **Автоматический мониторинг** по расписанию
- ✅ **Дневная статистика**: просмотры, форварды, ER
- ✅ **Рейтинг каналов**: по просмотрам, ER, активности, подписчикам
- ✅ **Поиск упоминаний** каналов в других каналах
- ✅ **Веб-дашборд** с графиками (Chart.js)
- ✅ **REST API** (FastAPI) — можно интегрировать куда угодно
- ✅ **Docker** — запуск одной командой

## 🏗 Архитектура

```
tgstat-opensource/
├── collector/       # Сбор данных с Telegram
│   ├── __init__.py  # Основной коллектор (Telethon)
│   └── scheduler.py # Планировщик (фоновый сбор)
├── db/
│   ├── __init__.py  # Инициализация БД
│   └── schema.py    # SQLAlchemy модели
├── api/
│   └── main.py      # FastAPI приложение + веб-дашборд
├── web/
│   └── dashboard.html  # Фронтенд (Chart.js)
├── config.yaml      # Конфигурация
├── Dockerfile       # Контейнеризация
└── requirements.txt # Зависимости
```

## 🛠 Быстрый старт

### 1. Получить API-ключи Telegram

1. Зайдите на https://my.telegram.org/apps
2. Создайте приложение → получите `api_id` и `api_hash`
3. Запомните свой номер телефона

### 2. Настройка

```bash
git clone https://github.com/ivanl2000/tgstat-opensource.git
cd tgstat-opensource
cp env_template.txt .env
nano .env  # заполните api_id, api_hash, phone
```

### 3. Запуск через Docker

```bash
docker build -t tgstat-opensource .
docker run -p 8080:8080 -v $(pwd)/data:/app/data tgstat-opensource
```

Откройте **http://localhost:8080** — дашборд готов!

### 4. Или напрямую

```bash
pip install -r requirements.txt
python -m api.main
```

## 📡 Сбор данных

### Разовый сбор для одного канала

```bash
python -m collector
# Введите username: @channel_name
```

### Фоновый мониторинг

Отредактируйте `config.yaml`, укажите каналы:

```yaml
collector:
  channels:
    - "@channel1"
    - "@channel2"
  fetch_interval_minutes: 60
  messages_per_run: 200
```

Запустите планировщик:

```bash
python -m collector.scheduler
```

## 📋 API endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/channels` | Список каналов |
| GET | `/api/channels/{id}` | Детали канала |
| GET | `/api/channels/{id}/stats?days=30` | Статистика по дням |
| GET | `/api/channels/{id}/posts?limit=50` | Посты канала |
| GET | `/api/rankings?sort_by=avg_views` | Рейтинг каналов |
| GET | `/api/search/mentions?query=@channel` | Поиск упоминаний |
| POST | `/api/collect?channel_username=@ch` | Запустить сбор |

## 📈 Метрики

- **Views** — просмотры поста
- **Forwards** — репосты
- **ER (Engagement Rate)** — `(просмотры + форварды) / подписчики × 100%`
- **Posts/day** — публикационная активность
- **Mentions** — сколько раз канал упомянули в других каналах

## 🗺 Roadmap

- [ ] Поиск по тексту постов
- [ ] График роста подписчиков
- [ ] Экспорт в CSV/Excel
- [ ] Telegram-бота для запросов
- [ ] Сравнение каналов бок-о-бок
- [ ] Категории каналов

## 🤝 Как помочь

1. Форкните репозиторий
2. Создайте ветку (`git checkout -b feature/awesome`)
3. Закоммитьте изменения (`git commit -am 'Add awesome feature'`)
4. Запушьте (`git push origin feature/awesome`)
5. Откройте Pull Request

## 📄 Лицензия

MIT License