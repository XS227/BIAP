# Iran-app files kept out of the Global bundle

These 13 files came from the Iran app and are not linked or imported by anything in the Global app.
They live outside `src/` so Metro/expo-router never bundles them, and `tsconfig.json` excludes `iran/`.
Nothing here is deleted or translated; the Iran app in `mobile/` is untouched.
Layout mirrors `src/` (`iran/src/app/*`, `iran/src/lib/*`, ...).
