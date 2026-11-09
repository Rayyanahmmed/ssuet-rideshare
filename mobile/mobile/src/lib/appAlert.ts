import { Alert, Platform, type AlertButton } from 'react-native';

/**
 * Cross-platform replacement for `Alert.alert`.
 *
 * React Native Web does not implement `Alert.alert`: it silently does nothing, so on the web
 * app a "Sign out" confirmation, error message or "Are you sure?" prompt simply never appeared.
 * On web this uses the browser's own `window.alert` / `window.confirm`, and the first
 * non-cancel button is the action that runs on confirm. Native keeps the real Alert.
 */
export function appAlert(title: string, message?: string, buttons?: AlertButton[]): void {
  if (Platform.OS !== 'web') {
    Alert.alert(title, message, buttons);
    return;
  }
  const text = [title, message].filter(Boolean).join('\n\n');
  const actions = (buttons ?? []).filter((button) => button.style !== 'cancel');

  if (actions.length === 0) {
    window.alert(text);
    return;
  }
  if ((buttons ?? []).length === 1) {
    window.alert(text);
    actions[0]?.onPress?.();
    return;
  }
  if (window.confirm(text)) {
    actions[0]?.onPress?.();
  }
}
