# mobile/ — Expo SDK 58 (primary product)

- Expo changes every SDK: read versioned docs `https://docs.expo.dev/versions/v58.0.0/` (or the `expo:*` skills) before using an Expo/RN API — do not rely on memory.
- Install packages with `npx expo install <pkg>` (SDK-compatible versions), never plain `pnpm add`.
- Routes in `src/app/` only; logic in hooks (`src/features/<feature>/use-*.ts`); API via `@/lib/api` (generated client, `just gen-client` — never hand-write API types).
- UI text from `@labtrack/shared/messages/{mn,en}.json` via `useTranslations`; no hard-coded strings. Mongolian is default.
- Styling: tokens from `@labtrack/shared` (`colors`, `space`, `fontSize`, `minTouchTarget`); styling library pending decision (docs/OPEN_QUESTIONS.md Q14). Flags = colour + glyph + text.
- Accessibility: `accessibilityRole`/`Label` on every control, touch targets ≥ 44pt/48dp, no fixed heights on text (Dynamic Type).
- Native modules → new dev build (`eas build --profile development`); OTA only for JS (`runtimeVersion: fingerprint`).
- Windows machine: no iOS simulator — Android emulator locally, iOS via EAS cloud build on a registered iPhone.

## Commands
- `pnpm --filter mobile test` (jest-expo + RNTL v14: `await render(...)`, `await fireEvent...`), `pnpm --filter mobile typecheck`, `npx expo-doctor` (in mobile/).
- `just mobile` starts Metro. Physical phone: set `CADDY_BIND=0.0.0.0` in `.env` (Caddy is localhost-only by default) and `EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8080`. Preview/production builds require an `https://` URL (build fails otherwise).
