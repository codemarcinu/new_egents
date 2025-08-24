#!/bin/bash

# =============================================================================
# 🤖 AGENT CHAT APP - SKRYPT ZATRZYMUJĄCY
# =============================================================================
# Ten skrypt bezpiecznie zatrzymuje wszystkie komponenty aplikacji
# Przeznaczony dla osób nietechnicznych
# =============================================================================

echo "🛑 Agent Chat App - Zatrzymywanie aplikacji..."
echo "==============================================="
echo ""

# Zatrzymaj serwer Django (Daphne)
echo "🌐 Zatrzymywanie serwera webowego..."
pkill -f "daphne.*8000" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Serwer webowy zatrzymany"
else
    echo "ℹ️  Serwer webowy nie był uruchomiony"
fi

# Zatrzymaj Celery worker
echo "⚙️  Zatrzymywanie procesora dokumentów..."
pkill -f "celery.*worker" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Procesor dokumentów zatrzymany"
else
    echo "ℹ️  Procesor dokumentów nie był uruchomiony"
fi

# Opcjonalnie zatrzymaj Redis (odkomentuj jeśli chcesz)
# echo "🔄 Zatrzymywanie serwera Redis..."
# redis-cli shutdown 2>/dev/null
# if [ $? -eq 0 ]; then
#     echo "✅ Redis zatrzymany"
# else
#     echo "ℹ️  Redis nie był uruchomiony lub jest używany przez inne aplikacje"
# fi

# Sprawdź czy wszystko zatrzymane
sleep 2
echo ""
echo "🔍 Sprawdzanie stanu aplikacji..."

DAPHNE_RUNNING=$(pgrep -f "daphne.*8000" | wc -l)
CELERY_RUNNING=$(pgrep -f "celery.*worker" | wc -l)

if [ $DAPHNE_RUNNING -eq 0 ] && [ $CELERY_RUNNING -eq 0 ]; then
    echo "✅ Wszystkie komponenty zatrzymane pomyślnie"
    echo ""
    echo "🎉 Aplikacja całkowicie zatrzymana!"
    echo "   Możesz bezpiecznie zamknąć terminal"
else
    echo "⚠️  Niektóre procesy mogą nadal działać:"
    if [ $DAPHNE_RUNNING -gt 0 ]; then
        echo "   - Serwer webowy ($DAPHNE_RUNNING proces/ów)"
    fi
    if [ $CELERY_RUNNING -gt 0 ]; then
        echo "   - Procesor dokumentów ($CELERY_RUNNING proces/ów)"
    fi
    echo ""
    echo "💡 Spróbuj uruchomić skrypt ponownie lub:"
    echo "   sudo killall daphne celery"
fi

echo ""
echo "==============================================="