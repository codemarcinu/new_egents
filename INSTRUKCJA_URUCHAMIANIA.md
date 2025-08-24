# 🚀 Jak uruchomić Agent Chat App - Instrukcja dla każdego!

## 📋 Wymagania przed pierwszym uruchomieniem

**WAŻNE:** Przed pierwszym użyciem skontaktuj się z administratorem systemu, aby upewnić się, że:
- ✅ Python i wszystkie biblioteki są zainstalowane
- ✅ Ollama i modele AI są skonfigurowane  
- ✅ Redis jest zainstalowany
- ✅ Aplikacja została prawidłowo skonfigurowana

## 🎯 Szybkie uruchamianie (dla codziennego użytku)

### **Krok 1: Otwórz terminal**
- **Linux/Mac:** Naciśnij `Ctrl+Alt+T` lub znajdź "Terminal" w aplikacjach
- **Windows:** Otwórz "Command Prompt" lub "PowerShell"

### **Krok 2: Przejdź do folderu z aplikacją**
```bash
cd /home/marcin/agent_chat_app
```

### **Krok 3: Uruchom aplikację**
```bash
./start_app.sh
```

### **Krok 4: Poczekaj na uruchomienie**
Zobaczysz komunikaty podobne do tych:
```
🤖 Agent Chat App - Uruchamianie aplikacji...
✅ Sprawdzanie katalogu... OK
✅ Sprawdzanie środowiska Python... OK
✅ Redis już działa
✅ Modele AI są dostępne
✅ Procesor dokumentów uruchomiony
🌐 Uruchamianie serwera webowego...

🎉 APLIKACJA JEST GOTOWA!
🔗 Otwórz przeglądarkę i przejdź do: http://127.0.0.1:8000/
```

### **Krok 5: Otwórz aplikację w przeglądarce**
1. Otwórz ulubioną przeglądarkę (Chrome, Firefox, Safari, Edge)
2. Wpisz adres: `http://127.0.0.1:8000/`
3. Zaloguj się:
   - **Login:** admin
   - **Hasło:** admin123

## 🛑 Zatrzymywanie aplikacji

### **Opcja 1: Z tego samego terminala**
W terminalu gdzie uruchomiłeś aplikację naciśnij: `Ctrl+C`

### **Opcja 2: Z nowego terminala**
```bash
cd /home/marcin/agent_chat_app
./stop_app.sh
```

## ❗ Najczęstsze problemy i rozwiązania

### **Problem: "command not found: ./start_app.sh"**
**Rozwiązanie:**
1. Sprawdź czy jesteś we właściwym folderze:
   ```bash
   pwd
   ```
   Powinieneś być w: `/home/marcin/agent_chat_app`

2. Jeśli nie, przejdź do właściwego folderu:
   ```bash
   cd /home/marcin/agent_chat_app
   ```

### **Problem: "Permission denied"**
**Rozwiązanie:**
```bash
chmod +x start_app.sh stop_app.sh
```

### **Problem: "Port 8000 is already in use"**
**Rozwiązanie:**
1. Najpierw zatrzymaj aplikację:
   ```bash
   ./stop_app.sh
   ```
2. Następnie uruchom ponownie:
   ```bash
   ./start_app.sh
   ```

### **Problem: "Redis not available"**
**Rozwiązanie:**
Skontaktuj się z administratorem - Redis musi być zainstalowany i skonfigurowany.

### **Problem: "Ollama models not found"**
**Rozwiązanie:**
Skrypt automatycznie pobierze modele przy pierwszym uruchomieniu. To może potrwać 10-30 minut w zależności od szybkości internetu. Bądź cierpliwy!

## 💡 Wskazówki dla łatwiejszego użytkowania

### **1. Utwórz skrót na pulpicie (Linux)**
```bash
# Stwórz plik na pulpicie
cat > ~/Desktop/start_chat_app.sh << 'EOF'
#!/bin/bash
cd /home/marcin/agent_chat_app
gnome-terminal -- bash -c "./start_app.sh; exec bash"
EOF

# Ustaw uprawnienia
chmod +x ~/Desktop/start_chat_app.sh
```

### **2. Sprawdź czy aplikacja działa**
Wpisz w przeglądarce: `http://127.0.0.1:8000/`
- Jeśli widzisz stronę logowania = ✅ wszystko działa
- Jeśli widzisz błąd = ❌ aplikacja nie działa

### **3. Automatyczne uruchamianie przy starcie systemu (opcjonalne)**
Skontaktuj się z administratorem, jeśli chcesz, aby aplikacja uruchamiała się automatycznie po włączeniu komputera.

## 📞 Kiedy skontaktować się z administratorem?

🔴 **Natychmiast skontaktuj się z pomocą techniczną gdy:**
- Skrypt pokazuje błędy o brakujących bibliotekach
- Nie możesz zainstalować/uruchomić Redis
- Ollama nie może pobrać modeli AI
- Aplikacja nie uruchamia się pomimo wykonania wszystkich kroków
- Widzisz błędy związane z bazą danych

🟡 **Możesz spróbować sam, ale w razie problemów poproś o pomoc:**
- Aplikacja działa wolno
- Dokumenty nie są przetwarzane
- Problemy z logowaniem

## ✅ Checklist codziennego użytkownika

**Przed rozpoczęciem pracy:**
- [ ] Uruchom terminal
- [ ] Przejdź do folderu aplikacji (`cd /home/marcin/agent_chat_app`)
- [ ] Uruchom aplikację (`./start_app.sh`)
- [ ] Poczekaj na komunikat "APLIKACJA JEST GOTOWA!"
- [ ] Otwórz przeglądarkę na `http://127.0.0.1:8000/`
- [ ] Zaloguj się (admin/admin123)

**Po zakończeniu pracy:**
- [ ] Naciśnij `Ctrl+C` w terminalu LUB uruchom `./stop_app.sh`
- [ ] Poczekaj na potwierdzenie zatrzymania
- [ ] Zamknij terminal

---

## 🎉 Gotowe!

Teraz możesz codziennie uruchamiać Agent Chat App jednym poleceniem i cieszyć się rozmowami z AI opartymi na Twoich dokumentach!

**Pamiętaj:** Jeśli coś nie działa, nie próbuj "naprawiać" samodzielnie - skontaktuj się z administratorem systemu.