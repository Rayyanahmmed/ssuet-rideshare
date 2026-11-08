import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Button, TextField } from '@/components/ui';
import { getApiBaseUrl } from '@/lib/config';
import {
  clearApiBaseUrlOverride,
  probeServer,
  saveApiBaseUrlOverride,
} from '@/lib/serverOverride';
import { colors, spacing, typography } from '@/theme';

/**
 * Testing-only control (rendered only when `EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE=1`).
 *
 * The APK bakes its API URL at build time; this lets QA re-point it at a laptop on the LAN
 * without another cloud build. The URL is stored in the keystore and survives restarts.
 */
export function ServerPanel() {
  const [value, setValue] = useState(getApiBaseUrl());
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSave = async () => {
    setBusy(true);
    try {
      const url = await saveApiBaseUrlOverride(value);
      setValue(url);
      setMessage(`Saved — ${url} is ${await probeServer(url)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Could not save the URL.');
    } finally {
      setBusy(false);
    }
  };

  const onReset = async () => {
    setBusy(true);
    try {
      const url = await clearApiBaseUrlOverride();
      setValue(url);
      setMessage(`Back to the build default — ${url}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Server (testing build)</Text>
      <Text style={styles.hint}>
        Phone and laptop must be on the same Wi-Fi. Example: http://192.168.100.32:8000/api/v1
      </Text>
      <TextField
        label="API base URL"
        placeholder="http://192.168.100.32:8000/api/v1"
        icon="server-outline"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        value={value}
        onChangeText={setValue}
      />
      {message ? <Text style={styles.message}>{message}</Text> : null}
      <View style={styles.row}>
        <Button label="Save & test" onPress={onSave} loading={busy} icon="checkmark-circle-outline" />
        <Button label="Reset" onPress={onReset} variant="secondary" icon="refresh-outline" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderColor: colors.border,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderRadius: 12,
    padding: spacing.md,
    gap: spacing.sm,
  },
  title: { color: colors.textMuted, ...typography.caption, textTransform: 'uppercase' },
  hint: { color: colors.textMuted, ...typography.caption },
  message: { color: colors.text, ...typography.caption },
  row: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
});
