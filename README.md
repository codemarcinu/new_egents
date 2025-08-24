# 🤖 Agent Chat App - Inteligentny Asystent z Dokumentami

**Agent Chat App** to nowoczesna aplikacja do rozmów z AI, która potrafi analizować i wykorzystywać Twoje dokumenty do udzielania bardziej precyzyjnych odpowiedzi. Aplikacja umożliwia przesyłanie dokumentów (PDF, Word, Excel, TXT), które są następnie "czytane" przez AI i wykorzystywane podczas rozmowy.

## 📋 Spis treści
- [Co to jest Agent Chat App?](#-co-to-jest-agent-chat-app)
- [Główne funkcje](#-główne-funkcje)
- [Jak to działa?](#-jak-to-działa)
- [Pierwsze kroki](#-pierwsze-kroki)
- [Jak korzystać z aplikacji](#-jak-korzystać-z-aplikacji)
- [Często zadawane pytania](#-często-zadawane-pytania)
- [Rozwiązywanie problemów](#-rozwiązywanie-problemów)
- [Informacje techniczne](#-informacje-techniczne)

## 🎯 Co to jest Agent Chat App?

Agent Chat App to aplikacja webowa, która łączy tradycyjny chatbot z zaawansowaną technologią analizy dokumentów. Dzięki temu AI może:

- **Rozmawiać** z Tobą w czasie rzeczywistym
- **Czytać i analizować** Twoje dokumenty
- **Odpowiadać na pytania** na podstawie treści dokumentów
- **Pamiętać** wcześniejsze rozmowy
- **Pracować jednocześnie** z wieloma użytkownikami

**Przykład użycia:** Przesyłasz raport sprzedaży z Excel, a następnie możesz zapytać: "Która kategoria produktów przyniosła najwięcej zysku w marcu?" - AI przeanalizuje dokument i odpowie na podstawie danych z pliku.

## 🌟 Główne funkcje

### 💬 Inteligentny Chat
- **Real-time rozmowy** - odpowiedzi AI pojawiają się natychmiast
- **Historia konwersacji** - wszystkie rozmowy są zapisywane
- **Wielokrotne sesje** - możesz prowadzić różne rozmowy na różne tematy
- **Wybór modelu AI** - możliwość wyboru spośród dostępnych modeli Ollama
- **Personalizacja** - ustawianie własnych instrukcji dla AI (system prompts)
- **Nowoczesny interfejs** - zoptymalizowany wygląd z intuicyjną nawigacją

### 📄 Analiza Dokumentów
- **Obsługiwane formaty:** PDF, Word (.docx), Excel (.xlsx), TXT
- **Automatyczne przetwarzanie** - dokumenty są analizowane w tle
- **Inteligentne wyszukiwanie** - AI znajduje odpowiednie fragmenty dokumentów
- **Bezpieczne przechowywanie** - każdy użytkownik ma dostęp tylko do swoich plików

### ⚡ Zaawansowane Technologie
- **RAG (Retrieval-Augmented Generation)** - AI wykorzystuje treść dokumentów
- **Asynchroniczne przetwarzanie** - możesz korzystać z aplikacji podczas analizy dokumentów
- **WebSocket** - natychmiastowa komunikacja
- **Responsywny design** - działa na komputerach, tabletach i telefonach

## 🔧 Jak to działa?

### 1. **Przesyłanie Dokumentu**
Gdy przesyłasz dokument:
- Plik jest bezpiecznie zapisywany na serwerze
- System automatycznie rozpoznaje typ pliku
- Rozpoczyna się proces analizy w tle

### 2. **Analiza i Indeksowanie**
- AI "czyta" treść dokumentu
- Dzieli tekst na mniejsze fragmenty (chunki)
- Tworzy "odciski palców" każdego fragmentu (embeddings)
- Zapisuje wszystko w bazie wektorowej

### 3. **Rozmowa z AI**
- Gdy zadajesz pytanie, AI szuka odpowiednich fragmentów w dokumentach
- Łączy znalezioną informację ze swoją wiedzą
- Udziela precyzyjnej odpowiedzi opartej na Twoich dokumentach

### 4. **Real-time Komunikacja**
- WebSocket zapewnia natychmiastową wymianę wiadomości
- Widzisz gdy AI "pisze" odpowiedź
- Wszystko dzieje się w czasie rzeczywistym

## 🚀 Pierwsze kroki

### Wymagania systemowe
- **System operacyjny:** Windows 10/11, macOS 10.15+, Ubuntu 20.04+
- **Przeglądarka:** Chrome, Firefox, Safari, Edge (najnowsze wersje)
- **Połączenie internetowe:** Stabilne połączenie do komunikacji z AI

### Logowanie
1. Otwórz przeglądarkę internetową
2. Przejdź pod adres: `http://127.0.0.1:8000/`
3. Zaloguj się używając danych:
   - **Login:** admin
   - **Hasło:** admin123

### Konfiguracja ustawień
Po zalogowaniu możesz dostosować swoje preferencje:
1. **Kliknij "Settings"** w menu głównym
2. **Wybierz model AI** z listy dostępnych modeli Ollama
3. **Ustaw instrukcje systemowe** - określ jak ma się zachowywać AI
4. **Dostosuj parametry** - temperatura (kreatywność) i maksymalna długość odpowiedzi
5. **Zapisz ustawienia** - będą używane we wszystkich nowych rozmowach

## 📖 Jak korzystać z aplikacji

### Przesyłanie dokumentów

1. **Kliknij "Upload Documents"** w menu głównym
2. **Wybierz plik** z komputera (PDF, Word, Excel lub TXT)
3. **Kliknij "Upload"** - zobaczysz potwierdzenie
4. **Poczekaj na przetworzenie** - może to potrwać od kilku sekund do kilku minut

> 💡 **Wskazówka:** Możesz kontynuować rozmowy podczas przetwarzania dokumentów

### Rozpoczynanie rozmowy

1. **Kliknij "New Chat"** aby rozpocząć nową konwersację
2. **Opcjonalnie zmień model** - kliknij przycisk "Model" i wybierz inny model AI
3. **Opcjonalnie ustaw tymczasową instrukcję** - kliknij ikonę ustawień i wpisz specjalne instrukcje dla tej rozmowy
4. **Wpisz pytanie** w pole tekstowe
5. **Naciśnij Enter** lub kliknij przycisk "Send"
6. **Poczekaj na odpowiedź** - AI przeanalizuje Twoje dokumenty

### Przykładowe pytania

**Dla dokumentów biznesowych:**
- "Jakie są główne wnioski z tego raportu?"
- "Ile wyniosły sprzedaże w ostatnim kwartale?"
- "Które produkty mają najwyższą marżę?"

**Dla dokumentów akademickich:**
- "Streść główne tezy tego artykułu"
- "Jakie są wyniki badań?"
- "Co autor rekomenduje?"

**Dla dokumentów prawnych:**
- "Jakie są kluczowe punkty tej umowy?"
- "Jakie są moje obowiązki?"
- "Kiedy wygasa ten dokument?"

### Zarządzanie konwersacjami

- **Lista rozmów** - po lewej stronie widzisz wszystkie swoje konwersacje
- **Przełączanie** - kliknij na konwersację aby ją otworzyć
- **Nowe rozmowy** - każdy temat może mieć własną konwersację
- **Historia** - wszystkie wiadomości są zapisywane automatycznie

## ❓ Często zadawane pytania

### **Q: Czy moje dokumenty są bezpieczne?**
A: Tak! Każdy użytkownik ma dostęp tylko do swoich dokumentów. Pliki są przechowywane lokalnie na serwerze i nie są udostępniane innym użytkownikom.

### **Q: Jak długo trwa przetwarzanie dokumentów?**
A: Zależy od rozmiaru pliku:
- Mały plik TXT (1-2 strony): kilka sekund
- Dokument Word (10-20 stron): 30-60 sekund
- Duży PDF (50+ stron): 2-5 minut
- Plik Excel z dużą ilością danych: 1-3 minuty

### **Q: Jakie formaty plików są obsługiwane?**
A: Obecnie obsługujemy:
- **PDF** - dokumenty, raporty, artykuły
- **Word (.docx)** - dokumenty tekstowe
- **Excel (.xlsx)** - arkusze kalkulacyjne, dane
- **TXT** - zwykłe pliki tekstowe

### **Q: Czy mogę przesłać kilka dokumentów naraz?**
A: Obecnie można przesyłać po jednym pliku na raz, ale możesz przesłać dowolną liczbę dokumentów - wszystkie będą dostępne podczas rozmowy.

### **Q: Co jeśli AI nie znajduje odpowiedzi w moich dokumentach?**
A: AI wykorzysta swoją ogólną wiedzę, ale zaznaczy, że informacja nie pochodzi z Twoich dokumentów. Możesz spróbować zadać pytanie inaczej lub przesłać dodatkowe dokumenty.

### **Q: Czy mogę usuwać dokumenty?**
A: Tak, w sekcji "Upload Documents" możesz zobaczyć listę wszystkich przesłanych plików i usunąć te, które nie są już potrzebne.

### **Q: Jak zmienić model AI podczas rozmowy?**
A: W interfejsie chatu kliknij przycisk "Model" w prawym górnym rogu i wybierz inny model z listy dostępnych. Zmiana zostanie zastosowana od następnej wiadomości.

### **Q: Co to są instrukcje systemowe?**
A: To personalne wskazówki dla AI określające jak ma się zachowywać - na przykład "Odpowiadaj jak ekspert finansowy" czy "Bądź kreatywny i używaj przykładów". Możesz je ustawiać globalnie w ustawieniach lub tymczasowo dla konkretnej rozmowy.

## 🔧 Rozwiązywanie problemów

### Problem: "Nie mogę się zalogować"
**Rozwiązanie:**
- Sprawdź czy używasz poprawnych danych: admin/admin123
- Upewnij się, że aplikacja jest uruchomiona
- Odśwież stronę przeglądarki

### Problem: "Dokument nie został przetworzony"
**Rozwiązanie:**
- Sprawdź czy plik ma obsługiwany format
- Upewnij się, że plik nie jest uszkodzony
- Poczekaj dłużej - duże pliki potrzebują więcej czasu
- Spróbuj przesłać plik ponownie

### Problem: "AI nie odpowiada na wiadomości"
**Rozwiązanie:**
- Sprawdź połączenie internetowe
- Odśwież stronę przeglądarki
- Sprawdź czy usługa Ollama jest uruchomiona (dla administratora)

### Problem: "Wolne działanie aplikacji"
**Rozwiązanie:**
- Zamknij niepotrzebne karty przeglądarki
- Upewnij się, że komputer ma wystarczająco pamięci RAM
- Sprawdź czy nie przetwarzasz zbyt wielu dokumentów jednocześnie

### Problem: "Nie widzę przesłanych dokumentów"
**Rozwiązanie:**
- Upewnij się, że jesteś zalogowany na właściwym koncie
- Odśwież stronę przeglądarki
- Sprawdź zakładkę "Upload Documents"

### Problem: "Lista modeli jest pusta"
**Rozwiązanie:**
- Sprawdź czy Ollama jest uruchomione
- Upewnij się, że masz zainstalowane modele (gemma3:4b, gpt-oss itp.)
- Skontaktuj się z administratorem systemu

## 💡 Wskazówki dla najlepszego doświadczenia

### Przygotowywanie dokumentów
- **Jakość skanów:** Upewnij się, że skany PDF są czytelne
- **Formatowanie:** Dokumenty Word z dobrym formatowaniem są łatwiej analizowane
- **Język:** Aplikacja najlepiej działa z dokumentami w języku angielskim i polskim
- **Rozmiar:** Dokumenty do 50MB działają najszybciej

### Zadawanie pytań
- **Bądź konkretny:** "Jakie były przychody w Q1?" zamiast "Powiedz mi o pieniądzach"
- **Używaj słów kluczowych:** Używaj terminów z dokumentów
- **Dziel złożone pytania:** Zadaj kilka prostszych pytań zamiast jednego skomplikowanego

### Organizacja pracy
- **Osobne rozmowy:** Twórz nową konwersację dla każdego tematu
- **Opisowe nazwy:** Rozmowy automatycznie otrzymują nazwy z pierwszej wiadomości
- **Regularne porządki:** Usuwaj stare dokumenty, których już nie potrzebujesz
- **Eksperymentuj z modelami:** Różne modele mają różne mocne strony - testuj który najlepiej sprawdza się w Twoim przypadku
- **Optymalizuj instrukcje:** Dopracowuj instrukcje systemowe aby uzyskać najlepsze rezultaty

## 🛠 Informacje techniczne

### Architektura systemu
- **Frontend:** HTML, CSS, JavaScript z Bootstrap 5 i Font Awesome
- **Backend:** Django (Python) z Django Channels
- **AI Models:** Ollama z obsługą wielu modeli (Gemma3, GPT-OSS, Qwen2.5VL, mxbai-embed)
- **Baza danych:** SQLite (lokalna) z modelami UserSettings
- **Wektory:** ChromaDB
- **Kolejkowanie:** Celery z Redis
- **WebSocket:** Real-time komunikacja z obsługą wyboru modeli

### Wymagania sprzętowe dla administratora
- **RAM:** minimum 8GB (16GB zalecane)
- **Procesor:** 4+ rdzenie
- **Dysk:** 10GB wolnej przestrzeni
- **GPU:** Opcjonalne, ale przyspiesza działanie AI

### Bezpieczeństwo
- **Autoryzacja:** Każdy użytkownik ma dostęp tylko do swoich danych
- **HTTPS:** Komunikacja może być szyfrowana
- **Lokalne przechowywanie:** Dokumenty nie opuszczają lokalnego serwera
- **Backup:** Regularne kopie zapasowe (konfigurowane przez administratora)

---

## 🏃‍♂️ Szybki start dla administratorów

### Instalacja i uruchomienie

1. **Sklonuj repozytorium:**
   ```bash
   git clone <repository-url>
   cd agent_chat_app
   ```

2. **Skonfiguruj środowisko:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # lub venv\Scripts\activate  # Windows
   pip install -r requirements/local_sqlite.txt
   ```

3. **Skonfiguruj bazę danych:**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Uruchom usługi:**
   ```bash
   # Terminal 1: Redis
   redis-server --daemonize yes --port 6379
   
   # Terminal 2: Celery Worker
   celery -A config.celery_app worker --loglevel=info --detach
   
   # Terminal 3: Django Server
   daphne -p 8000 config.asgi:application
   ```

5. **Skonfiguruj Ollama:**
   ```bash
   # Instaluj i uruchom modele
   ollama pull gemma3:4b
   ollama pull mxbai-embed-large
   ollama pull gpt-oss:latest
   ```

### Struktura projektu

```
agent_chat_app/
├── agent_chat_app/           # Główna aplikacja
│   ├── chat/                 # Moduł chatu i RAG
│   │   ├── models.py         # Modele danych
│   │   ├── views.py          # Widoki
│   │   ├── consumers.py      # WebSocket consumers
│   │   ├── tasks.py          # Celery tasks
│   │   ├── rag_service.py    # Serwis RAG
│   │   └── embeddings.py     # Serwis embeddingów
│   └── users/                # Zarządzanie użytkownikami
├── config/                   # Konfiguracja Django
│   ├── settings/             # Ustawienia środowisk
│   ├── urls.py              # URL routing
│   └── asgi.py              # ASGI konfiguracja
├── requirements/             # Zależności
├── media/                   # Przesłane pliki
└── templates/               # Szablony HTML
```

---

## 📞 Wsparcie

Jeśli potrzebujesz pomocy:

1. **Sprawdź FAQ** - większość problemów ma rozwiązanie powyżej
2. **Skontaktuj się z administratorem systemu** - jeśli problem persystuje
3. **Dokumentacja techniczna** - dostępna dla zespołu IT

---

**Aplikacja Agent Chat App została stworzona, aby ułatwić pracę z dokumentami i uczynić interakcję z AI bardziej użyteczną i efektywną.**

*Wersja dokumentacji: 1.1 | Data aktualizacji: 2025-08-24*
*Aktualizacja: Dodano funkcje wyboru modeli AI, ustawienia użytkownika i zoptymalizowany interfejs chatu*