import type { Href } from 'expo-router';

/** Minimal shape of expo-router's router, so this helper stays easy to unit-test. */
export interface BackCapableRouter {
  canGoBack: () => boolean;
  back: () => void;
  replace: (href: Href) => void;
}

/**
 * Back that never dead-ends. A screen opened from a push notification or a deep link has no
 * history, and `router.back()` then does nothing, leaving the user stuck on that screen.
 * In that case we land on the fallback (Home by default).
 */
export function goBackOr(router: BackCapableRouter, fallback: Href = '/(tabs)'): void {
  if (router.canGoBack()) {
    router.back();
  } else {
    router.replace(fallback);
  }
}
