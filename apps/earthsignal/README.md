# EarthSignal

Pierwsza wersja interfejsu do eksploracji wydarzeń i przyszłych analiz NISAR. React, TypeScript, Vite i MapLibre GL JS. Aplikacja statyczna, bez kluczy i serwera API.

## Uruchomienie

Wymagany Node.js 22.12+ (testy TypeScript bez kompilacji: Node 22.18+ lub 24+).

```sh
npm ci
npm run dev
```

```sh
npm test
npm run build
```

Build znajduje się w `dist/`. Serwować jako statyczną stronę. Worker MapLibre jest pakowany lokalnie przez Vite; dane granic państw znajdują się w `public/countries.geojson`.

## Funkcje

- Przesuwana i przybliżana mapa z kategoriami i klikalnymi hotspotami.
- Wyszukiwanie, filtry kategorii i dat, kandydatów udokumentowanych oraz zasięgu widoku.
- Karty wydarzeń, źródła i dostępne daty obserwacji kandydatów.
- Statystyki katalogu i wykres miesięczny dla widocznych punktów; kliknięcie miesiąca filtruje katalog.
- Animowany astronauta, lokalny czat PL/EN i trzyetapowy przewodnik.
- Obsługa małych ekranów, klawiatury, ograniczenia animacji i pustych wyników.

## Status danych i ograniczenia v0.1

Katalog zawiera 4 udokumentowane kandydatury studiów oraz 9 fikstur demonstracyjnych. Wpisy scenariuszowe nie są potwierdzeniem wystąpienia katastrofy. Daty obserwacji kandydatów pochodzą z wcześniejszego researchu w katalogu ASF/CMR.

Zgodnie z ustalonym zakresem rzeczywiste studium ma być wybrane w kolejnym etapie. Nie ma jeszcze rastrów NISAR, porównania pikselowego before/after, pomiarów skutków, przetwarzania HDF5 ani danych czasu rzeczywistego. Dolny wykres przedstawia **wpisy katalogu**, nie szereg pomiarów satelitarnych.

Orbit jest lokalnym nawigatorem opartym na rozpoznawaniu słów i aliasów. Nie korzysta z LLM ani z sieci. Przykłady: „Wskaż pożary w Hiszpanii”, „Floods in Mozambique”, „Earthquakes in Japan”, „Guide me”. Nie jest to pełny parser języka naturalnego; nie obsługuje każdego miejsca i dowolnej odmiany nazw.

## Podłączenie rzeczywistego przypadku

1. Wybrać AOI, produkt, daty, metodę i referencję walidacyjną.
2. Przygotować numeryczne rastry/COG, maski i warstwy wizualne.
3. Rozszerzyć `EventRecord` o manifest analizy i wdrożyć komponent porównania oraz API statystyk rastrowych.
4. Zastąpić metryki katalogowe metrykami studium wyłącznie w jego kontekście.
5. Dodać backend FastAPI i kontrolowane narzędzia LLM. Klucz API pozostaje po stronie serwera.

## Źródła

Granice: Natural Earth, public domain, skala 1:110m. Źródłowy plik: https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson . Zachowano geometrię, ograniczono właściwości do nazwy kraju. Granice są poglądowe i nie służą do precyzyjnych pomiarów.

Źródła wydarzeń znajdują się w `src/domain.ts`. Ilustracja astronauty: własny SVG. Fonty DM Sans i Manrope ładowane z Google Fonts; systemowy fallback działa bez tego połączenia. MapLibre: BSD-3-Clause; pozostałe zależności zachowują własne licencje.
