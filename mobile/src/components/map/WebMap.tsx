import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { MapSurface, type MapSurfaceHandle } from '@/components/map/MapSurface';
import { Ionicons } from '@expo/vector-icons';
import { getMapConfig, tileBaseUrl, type MapConfig } from '@/api/maps';
import { buildTileMapHtml, type MapPin } from '@/components/map/tileMapHtml';
import { colors, radius, spacing, typography } from '@/theme';

/**
 * The app's map (§13) — a WebView rendering tiles served by our own API.
 *
 * Nothing about the provider is baked into the APK: the screen asks `/maps/config` which
 * provider to use and requests every tile from `/maps/tiles/{z}/{x}/{y}.png`, where the key is
 * injected server-side. An administrator can therefore rotate the key (or switch provider
 * entirely) and this map keeps working — no rebuild, no new APK, no `.env` edit.
 */

type Props = {
  latitude: number;
  longitude: number;
  /** Extra pins to draw; the first one is the draggable pickup pin when `editable`. */
  pins?: MapPin[];
  editable?: boolean;
  fit?: boolean;
  height?: number;
  hint?: string;
  onPin?: (latitude: number, longitude: number) => void;
};

export function WebMap({
  latitude,
  longitude,
  pins,
  editable = false,
  fit = false,
  height = 190,
  hint,
  onPin,
}: Props) {
  const webview = useRef<MapSurfaceHandle>(null);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [ready, setReady] = useState(false);

  const configQuery = useQuery({
    queryKey: ['maps', 'config'],
    queryFn: getMapConfig,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const config: MapConfig | undefined = configQuery.data;
  const mapReady = Boolean(config?.enabled) && (!config?.needs_key || Boolean(config?.has_key));

  const html = useMemo(() => {
    if (!config) return '';
    return buildTileMapHtml({
      tileBase: tileBaseUrl(),
      attribution: config.attribution,
      latitude,
      longitude,
      zoom: fit ? 12 : 15,
      pins: pins ?? [{ id: 'pickup', latitude, longitude, color: colors.green }],
      editable,
      fit,
      hint,
    });
  }, [config, latitude, longitude, pins, editable, fit, hint]);

  /** Keep the pin in step when the screen changes the point from outside (GPS, area chip). */
  useEffect(() => {
    if (!ready) return;
    webview.current?.inject(
      `window.__map && window.__map.setPin(${latitude}, ${longitude}); true;`,
    );
  }, [latitude, longitude, ready]);

  const handleMessage = useCallback(
    (raw: string) => {
      let payload: { type?: string; latitude?: number; longitude?: number } = {};
      try {
        payload = JSON.parse(raw);
      } catch {
        return;
      }
      if (payload.type === 'ready') {
        setReady(true);
      } else if (payload.type === 'tiles-error') {
        setTilesFailed(true);
      } else if (payload.type === 'pin' && typeof payload.latitude === 'number' && typeof payload.longitude === 'number') {
        onPin?.(payload.latitude, payload.longitude);
      }
    },
    [onPin],
  );

  const shell = (children: React.ReactNode) => <View style={[styles.wrap, { height }]}>{children}</View>;

  if (configQuery.isLoading) {
    return shell(
      <View style={styles.notice}>
        <ActivityIndicator size="small" color={colors.navy} />
        <Text style={styles.noticeText}>Loading map…</Text>
      </View>,
    );
  }

  if (configQuery.isError || !config) {
    return shell(
      <View style={styles.notice}>
        <Ionicons name="cloud-offline-outline" size={20} color={colors.textMuted} />
        <Text style={styles.noticeText}>
          Map could not load — the server is unreachable. Area search still works.
        </Text>
      </View>,
    );
  }

  if (!mapReady) {
    return shell(
      <View style={styles.notice}>
        <Ionicons name="warning-outline" size={20} color={colors.warning} />
        <Text style={styles.noticeText}>
          {config.enabled
            ? `Map provider (${config.provider}) has no API key. An administrator can add one under Admin → Map API; no app update is needed.`
            : 'Maps are switched off in the admin console. Choose an area instead.'}
        </Text>
      </View>,
    );
  }

  return shell(
    <View style={styles.frame}>
      <MapSurface
        ref={webview}
        key={`${config.provider}-${config.updated_at ?? 'init'}`}
        html={html}
        onMessage={handleMessage}
        onTilesError={() => setTilesFailed(true)}
      />
      {tilesFailed ? (
        <Pressable
          style={styles.retry}
          onPress={() => {
            setTilesFailed(false);
            webview.current?.inject('window.__map && window.__map.refresh(); true;');
          }}
        >
          <Ionicons name="refresh" size={13} color={colors.navy} />
          <Text style={styles.retryText}>Tiles did not load — tap to retry</Text>
        </Pressable>
      ) : null}
    </View>,
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: spacing.xs,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.surfaceAlt,
  },
  frame: { flex: 1, borderRadius: radius.md, overflow: 'hidden' },
  notice: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surfaceAlt,
  },
  noticeText: { flex: 1, color: colors.textMuted, ...typography.caption },
  retry: {
    position: 'absolute',
    left: 8,
    right: 8,
    bottom: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 6,
    borderRadius: radius.sm,
    backgroundColor: 'rgba(255,255,255,0.94)',
    borderWidth: 1,
    borderColor: colors.border,
  },
  retryText: { color: colors.navy, ...typography.caption, fontWeight: '600' },
});
