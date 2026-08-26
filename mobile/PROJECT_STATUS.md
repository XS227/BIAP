# BIAP Mobile — Project Status

_Last updated: 2026-07-21_

## Architecture

- **Framework:** Expo SDK 54 (React Native 0.81.5, React 19.1.0), file-based routing via `expo-router` (`src/app/`).
- **Entry:** `expo-router/entry` → `src/app/_layout.tsx` gates the app between `LoginScreen` and `AppTabs` based on an `accessToken` stored in `AsyncStorage`.
- **Navigation:** Bottom tab bar (`src/components/app-tabs.tsx`, `expo-router` `<Tabs>`) with 4 visible tabs plus 2 hidden stack routes:
  - `index` (بورس / Stock) — `src/app/index.tsx`
  - `bizdev` (کسب‌وکار / Business) — `src/app/bizdev.tsx`
  - `data` (داده / Data) — `src/app/data.tsx`
  - `profile` (حساب / Account) — `src/app/profile.tsx`
  - `stock/[code]` — stock detail screen, hidden from tab bar (`href: null`), reached via `router.push`
  - `register` — hidden from tab bar, reached from the login screen
- **API layer:** `src/lib/api.ts` — single `fetchWatchlist()` helper wrapping `GET /stock/watchlist` with a Bearer token (from `AsyncStorage`) and a 10s `AbortController` timeout. All four tabs and the stock detail screen consume this same function.
- **State/data flow:** No global state library — each screen manages its own `useState`/`useEffect`/`useCallback` fetch-and-poll cycle (`index.tsx` polls every 30s, `bizdev.tsx` every 60s, `stock/[code].tsx` every 30s; `data.tsx` fetches once + pull-to-refresh).
- **Auth:** Email/password login and registration hit `${API_BASE}/auth/login` and `${API_BASE}/auth/register`. On success, `accessToken` and `user` (JSON) are stored in `AsyncStorage`. Logout clears both via `AsyncStorage.multiRemove` and is exposed app-wide through `src/lib/logout-context.ts` (`LogoutContext`), consumed from the profile screen.
- **Styling/theming:** `src/constants/theme.ts` defines light/dark color tokens, brand accent colors per tab, spacing scale, and platform-specific fonts (Vazirmatn for Farsi text). `useColorScheme` drives light/dark automatically.
- **Fonts:** Vazirmatn (Farsi) loaded via `@expo-google-fonts/vazirmatn` in `_layout.tsx`, gating render until loaded.

## Working features (verified)

- **Login** — email/password against the live backend, error messaging on failure, loading spinner, persists session to `AsyncStorage`.
- **Register** — client-side validation (email format, password length/match), success screen routing back to login.
- **Logout** — confirmation dialog, clears stored token/user, routes back to login screen.
- **Stock tab** — live watchlist with scrolling ticker, search/filter, market-open status pill, 30s auto-refresh with visible countdown, pull-to-refresh, tap-through to stock detail.
- **Business tab** — market sentiment summary (gainers/losers/unchanged), top gainer/loser highlight, sortable full symbol list (by % change / price / name).
- **Data tab** — bar chart and % change chart, full data table, aggregate stats (avg price, max/min %, std dev), CSV export (native share sheet on iOS/Android via `expo-sharing`, browser download on web).
- **Account tab** — user avatar/initials, profile info card, app info card (name/version/API host), logout.
- **Stock detail screen** — price card, mini price-comparison chart, full info table, "not found" state if the code isn't in the watchlist, 30s auto-refresh, pull-to-refresh.
- **Loading / empty / error / retry states** — present on every data screen: skeleton rows while loading, Farsi error banner on fetch failure, `RefreshControl` (pull-to-refresh) as the retry mechanism, and Farsi "no data" empty state.

## API & servers

- **API base URL:** `https://biap.dadashi.no/api` (`src/lib/api.ts`)
- **Backend server:** `89.42.199.20` — **not modified by this pass.**
- **Mobile/Expo dev server:** this VPS (`5.249.252.221`) — Expo CLI + Metro bundler, exposed to Expo Go over an `@expo/ngrok` tunnel (no LAN/same-network requirement).

## Test credentials

- Use your own registered account, or ask the project owner for a shared test login.
- **Never store the real password in this file, in source, or in git.** Placeholder only:
  - Email: `test@example.com`
  - Password: `••••••••` (placeholder — real credentials are not committed anywhere in this repo)

## Running the app

From `/home/nasrin/Biap/mobile` on the VPS:

```bash
# install deps (only needed after a fresh clone or dependency change)
npm install

# start the Expo dev server with a public tunnel (required — phone and VPS are not on the same network)
npx expo start --tunnel
```

Then in Expo Go on the phone, scan the QR code or open the `exp://` URL printed in the terminal (format: `exp://<random>-anonymous-8081.exp.direct`, changes on every restart unless run under a fixed Expo account/EAS Update).

Other useful commands:

```bash
npx tsc --noEmit      # TypeScript check
npx expo-doctor        # Expo project health check
npx expo lint           # ESLint
```

## Known issues / dependency notes

- `expo-doctor` reports `typescript@6.0.3` and `@types/react@19.2.17` as ahead of the versions Expo SDK 54 officially pins (`~5.9.2` / `~19.1.10`). Left as-is intentionally: both are dev-only (no effect on the shipped bundle), and `npx tsc --noEmit` passes cleanly against the newer versions. Downgrading a major TypeScript version was judged higher-risk than the mismatch itself.
- `expo-file-system` and `expo-sharing` were previously drifted to unrelated-major versions (`57.x`) that don't track the Expo SDK's own versioning, causing a duplicate-native-module warning from `expo-doctor`. Fixed in this pass by realigning to the SDK-54-compatible versions (`expo-file-system@~19.0.23`, `expo-sharing@~14.0.8`) via `npx expo install`. The CSV export feature on the Data tab (which uses `expo-file-system/legacy`) was verified to still expose the same API (`documentDirectory`, `writeAsStringAsync`, `EncodingType`) after the downgrade.
- No automated test suite exists yet (no Jest config in this project).
- No CI/lint-on-push configured.

## Next recommended tasks

1. Add a minimal Jest + React Native Testing Library setup for the API layer (`src/lib/api.ts`) and one or two screens.
2. Consider centralizing the repeated fetch/loading/error/refresh boilerplate (near-identical across `index.tsx`, `bizdev.tsx`, `data.tsx`, `stock/[code].tsx`) into a small shared hook, e.g. `useWatchlist()`.
3. Pin the Expo tunnel to a stable hostname (EAS/Expo account login + `expo start --tunnel` under that account) so the Expo Go URL doesn't change on every server restart.
4. Revisit `typescript`/`@types/react` versions the next time Expo SDK is upgraded, so the project stays aligned with upstream expectations rather than accumulating further drift.
