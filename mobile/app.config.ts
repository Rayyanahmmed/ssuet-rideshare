import type { ExpoConfig, ConfigContext } from 'expo/config';

/**
 * Expo configuration (§24).
 *
 * Everything environment-specific comes from EXPO_PUBLIC_* variables so the
 * same source builds dev / preview / production artefacts.
 * Never hardcode API URLs, map keys or secrets here.
 */
// A cloud build runs on Expo's machines and never sees the local .env, so the fallback must
// not be `localhost` there. EAS_BUILD_PROFILE is only set inside an EAS build.
const FALLBACK_API_URL = process.env.EAS_BUILD_PROFILE
  ? 'https://ssuet-rideshare-api.onrender.com/api/v1'
  : 'http://localhost:8000/api/v1';

// Testing builds (`EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`) let QA change the API URL inside
// the app; such a build may talk to a laptop over plain HTTP, which Android blocks by
// default — so the cleartext allowance is enabled only alongside that flag.
const ALLOW_SERVER_OVERRIDE = process.env.EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE === '1';

const testingPlugins: [string, Record<string, unknown>][] = ALLOW_SERVER_OVERRIDE
  ? [['expo-build-properties', { android: { usesCleartextTraffic: true } }]]
  : [];

// `EAS_PROJECT_ID=` in a .env file is an empty string, and `??` does not treat that as
// "unset" — so every value goes through a helper that trims and falls back.
const envOr = (value: string | undefined, fallback: string): string => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
};

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  // The Expo account that owns the EAS project. Required when an account belongs to more
  // than one (personal + team), otherwise EAS may resolve the project under the wrong owner.
  owner: 'rayyanahmedkhan',
  name: 'SSUET RideShare',
  slug: 'ssuet-rideshare',
  version: '1.0.0',
  orientation: 'portrait',
  scheme: 'ssuetrideshare',
  userInterfaceStyle: 'light',
  newArchEnabled: true,
  icon: './assets/icon.png',
  splash: {
    image: './assets/splash.png',
    resizeMode: 'contain',
    backgroundColor: '#0B1F3A',
  },
  android: {
    package: 'com.ssuet.rideshare',
    // versionCode intentionally omitted: eas.json sets appVersionSource "remote", so EAS
    // owns the number. A local value here is ignored and only produces a build warning.
    adaptiveIcon: {
      foregroundImage: './assets/adaptive-icon.png',
      backgroundColor: '#0B1F3A',
    },
    permissions: [
      'ACCESS_FINE_LOCATION',
      'ACCESS_COARSE_LOCATION',
      'POST_NOTIFICATIONS',
      'INTERNET',
    ],
  },
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'com.ssuet.rideshare',
  },
  plugins: [
    [
      'expo-image-picker',
      {
        photosPermission:
          'SSUET RideShare uses your photo library only to attach a picture of your student or employee card for verification.',
        cameraPermission:
          'SSUET RideShare uses the camera only to photograph your student or employee card for verification.',
      },
    ],
    'expo-router',
    'expo-secure-store',
    'expo-notifications',
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'SSUET RideShare uses your location to suggest pick-up areas near you. Your exact position is never shared with other members.',
      },
    ],
    ...testingPlugins,
  ],
  // Browser build (Vercel): a single-page app, so every URL falls back to index.html.
  web: {
    bundler: 'metro',
    output: 'single',
    name: 'SSUET RideShare',
    shortName: 'SSUET',
    themeColor: '#0B1F3A',
    backgroundColor: '#F4F6F8',
  },
  experiments: {
    typedRoutes: true,
    // Keep Metro's own tsconfig `paths` support on as well — babel.config.js also maps
    // `@/*` with babel-plugin-module-resolver, so the alias resolves on every machine.
    tsconfigPaths: true,
  },
  extra: {
    apiUrl: envOr(process.env.EXPO_PUBLIC_API_URL, FALLBACK_API_URL),
    // Maps are rendered from server-proxied tiles (§13): there is no map key in the build.

    // Renders the "Server (testing build)" panel on the auth screens.
    allowServerOverride: ALLOW_SERVER_OVERRIDE,
    // EAS cannot write into a *dynamic* config (app.config.ts), so the project id has a
    // default here, and EAS_PROJECT_ID in the environment can still override it.
    // Project: https://expo.dev/accounts/rayyanahmedkhan/projects/ssuet-rideshare
    eas: {
      projectId: envOr(process.env.EAS_PROJECT_ID, '11fd9726-022e-4f5a-8690-48deb063f925'),
    },
  },
});
