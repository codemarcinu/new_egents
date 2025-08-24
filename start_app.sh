#!/bin/bash

# =============================================================================
# 🤖 AGENT CHAT APP - SKRYPT URUCHAMIAJĄCY
# =============================================================================
# Ten skrypt uruchamia wszystkie komponenty aplikacji Agent Chat App
# Przeznaczony dla osób nietechnicznych - po prostu uruchom i czekaj!
# =============================================================================

echo "🤖 Agent Chat App - Uruchamianie aplikacji..."
echo "================================================"
echo ""

# Sprawdź czy jesteśmy w odpowiednim katalogu
if [ ! -f "manage.py" ]; then
    echo "❌ BŁĄD: Nie jesteś w katalogu projektu!"
    echo "   Przejdź do katalogu: /home/marcin/agent_chat_app"
    echo "   Następnie uruchom ponownie skrypt"
    exit 1
fi

echo "✅ Sprawdzanie katalogu... OK"

# Sprawdź czy środowisko wirtualne istnieje
if [ ! -d "venv" ]; then
    echo "❌ BŁĄD: Brak środowiska wirtualnego!"
    echo "   Skontaktuj się z administratorem systemu"
    exit 1
fi

echo "✅ Sprawdzanie środowiska Python... OK"

# Aktywuj środowisko wirtualne
source venv/bin/activate
echo "✅ Aktywacja środowiska Python... OK"

# Sprawdź czy Redis jest dostępny
if ! command -v redis-server &> /dev/null; then
    echo "❌ BŁĄD: Redis nie jest zainstalowany!"
    echo "   Skontaktuj się z administratorem systemu"
    exit 1
fi

# Uruchom Redis jeśli nie działa
if ! redis-cli ping &> /dev/null; then
    echo "🚀 Uruchamianie serwera Redis..."
    redis-server --daemonize yes --port 6379
    sleep 2
    
    if redis-cli ping &> /dev/null; then
        echo "✅ Redis uruchomiony pomyślnie"
    else
        echo "❌ BŁĄD: Nie można uruchomić Redis"
        exit 1
    fi
else
    echo "✅ Redis już działa"
fi

# Sprawdź czy Ollama jest dostępne
if ! command -v ollama &> /dev/null; then
    echo "⚠️  OSTRZEŻENIE: Ollama nie jest zainstalowane!"
    echo "   Aplikacja może nie działać poprawnie bez modeli AI"
    echo "   Skontaktuj się z administratorem systemu"
fi

# Sprawdź czy modele Ollama są dostępne
if command -v ollama &> /dev/null; then
    echo "🧠 Sprawdzanie modeli AI..."
    if ! ollama list | grep -q "gemma2:2b"; then
        echo "⚠️  OSTRZEŻENIE: Model gemma2:2b nie jest zainstalowany"
        echo "   Pobieranie modelu... (to może potrwać kilka minut)"
        ollama pull gemma2:2b
    fi
    
    if ! ollama list | grep -q "mxbai-embed-large"; then
        echo "⚠️  OSTRZEŻENIE: Model mxbai-embed-large nie jest zainstalowany"
        echo "   Pobieranie modelu... (to może potrwać kilka minut)"
        ollama pull mxbai-embed-large
    fi
    echo "✅ Modele AI są dostępne"
fi

# Uruchom migracje bazy danych (na wszelki wypadek)
echo "🗄️  Aktualizacja bazy danych..."
python manage.py migrate --run-syncdb > /dev/null 2>&1

# Sprawdź czy istnieje użytkownik admin
echo "👤 Sprawdzanie użytkownika admin..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    print('Tworzenie użytkownika admin...')
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('✅ Użytkownik admin utworzony (login: admin, hasło: admin123)')
else:
    print('✅ Użytkownik admin już istnieje')
" 2>/dev/null

# Uruchom Celery worker w tle
echo "⚙️  Uruchamianie procesora dokumentów (Celery)..."
pkill -f "celery.*worker" 2>/dev/null  # Zatrzymaj poprzednie instancje
celery -A config.celery_app worker --loglevel=info --detach > /dev/null 2>&1

if pgrep -f "celery.*worker" > /dev/null; then
    echo "✅ Procesor dokumentów uruchomiony"
else
    echo "❌ BŁĄD: Nie można uruchomić procesora dokumentów"
    exit 1
fi

# Sprawdź czy port 8000 jest wolny
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Port 8000 jest zajęty. Zatrzymywanie poprzedniej instancji..."
    pkill -f "daphne.*8000" 2>/dev/null
    sleep 2
fi

# Uruchom serwer Django
echo "🌐 Uruchamianie serwera webowego..."
echo ""
echo "🎉 APLIKACJA JEST GOTOWA!"
echo "================================================"
echo "🔗 Otwórz przeglądarkę i przejdź do:"
echo "   http://127.0.0.1:8000/"
echo ""
echo "👤 Dane do logowania:"
echo "   Login: admin"
echo "   Hasło: admin123"
echo ""
echo "📝 Aby zatrzymać aplikację:"
echo "   Naciśnij Ctrl+C w tym oknie"
echo "   LUB uruchom skrypt: ./stop_app.sh"
echo ""
echo "================================================"
echo "🚀 Uruchamianie... (czekaj na komunikat 'Listening')"
echo ""

# Uruchom serwer Django (będzie działał do momentu przerwania)
daphne -p 8000 config.asgi:application

# Po zakończeniu serwera (Ctrl+C) posprzątaj
echo ""
echo "🛑 Zatrzymywanie aplikacji..."

# Zatrzymaj Celery worker
echo "⚙️  Zatrzymywanie procesora dokumentów..."
pkill -f "celery.*worker" 2>/dev/null

echo "✅ Aplikacja zatrzymana pomyślnie"
echo "   Można bezpiecznie zamknąć to okno"