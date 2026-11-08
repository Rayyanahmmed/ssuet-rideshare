# mobile/ — SSUET RideShare (Expo + React Native + TypeScript)

**Phases 1–2 complete.** Authentication is wired end-to-end: onboarding, signup,
login, forgot-password, keystore sessions, silent token refresh, a verified-only
gate for the ride features, and the five-tab shell with a real profile screen.

## Run

```bash
npm install
cp .env.example .env            # EXPO_PUBLIC_API_URL=http://<YOUR_LAN_IP>:8000/api/v1
npx expo start                  # press "a" for Android
```

Sign in with a seeded account (e.g. `ali@ssuet.edu.pk` / `Password123!`) or
register a new one — any `@ssuet.edu.pk` address is verified instantly.

## Build an APK (EAS)

```bash
npm install -g eas-cli && eas login
eas build:configure
eas build --platform android --profile preview     # installable APK
```

## Structure

```
app/
  index.tsx              launch gate (keystore → GET /auth/me → redirect)
  (auth)/welcome         onboarding (3 slides)
  (auth)/login           email + password (React Hook Form + Zod)
  (auth)/signup          role, department, student/teacher fields
  (auth)/forgot-password reset link request
  (tabs)/index           Home: greeting, campus card, search, verification banner
  (tabs)/explore         filters + honest empty state (rides arrive in Phase 3)
  (tabs)/publish         5-step flow preview
  (tabs)/my-rides        5 status tabs
  (tabs)/profile         real profile, stats, verification, sign out
  verification.tsx       manual university-ID submission
src/
  api/client.ts          axios + single-flight refresh + ApiError envelope
  api/auth.ts            typed auth calls
  components/ui          design-system primitives (Button, TextField, Card, Badge…)
  lib/schemas.ts         Zod schemas mirroring the backend
  lib/secureStore.ts     expo-secure-store token persistence
  store/auth.ts          Zustand session (hydrate / completeSignIn / signOut)
  theme/index.ts         navy · green · white tokens
```

## Notes

* Tokens never touch AsyncStorage: they live in the Android Keystore / iOS Keychain.
* A `401` triggers exactly one refresh; concurrent failures queue on the same promise.
* Screens that will hold API data in later phases already ship loading, empty and
  error states — they never display invented rides or statistics.
