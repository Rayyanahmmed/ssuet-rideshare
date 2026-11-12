import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { TextField } from '@/components/ui';
import { WebMap } from '@/components/map/WebMap';
import { reverseGeocode, searchPlaces } from '@/api/maps';
import { AREAS, findArea, SSUET, type AreaPoint } from '@/lib/areas';
import { colors, radius, spacing, typography } from '@/theme';

type Props = {
  label: string;
  value: string;
  point: AreaPoint | null;
  onChange: (area: string, point: AreaPoint) => void;
  error?: string;
};

/**
 * Area + location picker (§13).
 *
 * * Always available: search/choose a Karachi area → its centroid is used.
 * * The map is a **WebView** fed by our own tile proxy, so the provider and its API key are
 *   chosen in the admin dashboard — an expired key never blanks the map in a shipped APK.
 * * Tapping the map drops the pin; dragging the pin fine-tunes it; the area name is filled
 *   in by the backend's reverse geocoder.
 * * "Use my current location" uses expo-location, with a friendly failure path.
 */

/** Turn "Pixy, University Road, Gulshan-e-Iqbal Block 13 C, Karachi…" into a short area name. */
function shortAreaName(label: string): string {
  if (!label) return '';
  const parts = label
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  const known = AREAS.find((area) =>
    parts.some((part) => part.toLowerCase().includes(area.name.toLowerCase())),
  );
  if (known) return known.name;
  const short = parts.slice(0, 2).join(', ');
  return short.length > 48 ? `${short.slice(0, 45)}…` : short;
}

export function LocationPicker({ label, value, point, onChange, error }: Props) {
  const [locating, setLocating] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [permissionNote, setPermissionNote] = useState<string | null>(null);

  const selectArea = (areaName: string) => {
    const centroid = findArea(areaName) ?? SSUET;
    onChange(areaName, { ...centroid, name: areaName });
  };

  const useCurrentLocation = async () => {
    setPermissionNote(null);
    setLocating(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setPermissionNote('Location permission denied — pick an area or tap the map instead.');
        return;
      }
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const guess = await Location.reverseGeocodeAsync(position.coords).catch(() => []);
      const areaName =
        guess[0]?.district ?? guess[0]?.subregion ?? guess[0]?.city ?? value ?? 'Current location';
      onChange(areaName, {
        name: areaName,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
    } catch {
      setPermissionNote('Could not read your location. Choose an area or tap the map instead.');
    } finally {
      setLocating(false);
    }
  };

  /** A tap or pin-drag inside the WebView map. */
  const handlePin = async (latitude: number, longitude: number) => {
    setResolving(true);
    let areaName = value.trim();
    try {
      const place = await reverseGeocode(latitude, longitude);
      areaName = shortAreaName(place.label) || areaName;
    } catch {
      // Offline or geocoder down — the coordinates still count.
      if (!areaName) areaName = 'Pinned location';
    }
    onChange(areaName || 'Pinned location', { name: areaName || 'Pinned location', latitude, longitude });
    setResolving(false);
  };

  const centre = point ?? SSUET;

  /**
   * Typed address → look it up on the server and move the pin there. Exact area names are
   * answered from the local list; anything else waits for the user to pause typing.
   */
  const searchSeq = useRef(0);
  const typedRef = useRef(false);
  useEffect(() => {
    // Only text the user typed moves the pin. Map taps and GPS fill the name themselves, and
    // must not be overridden by a lookup of that name.
    if (!typedRef.current) return;
    typedRef.current = false;
    const query = value.trim();
    if (query.length < 3 || findArea(query)) return;
    const seq = ++searchSeq.current;
    const timer = setTimeout(() => {
      searchPlaces(query, 1)
        .then((results) => {
          if (seq !== searchSeq.current || results.length === 0) return;
          const best = results[0]!;
          onChange(query, { name: query, latitude: best.latitude, longitude: best.longitude });
        })
        .catch(() => undefined); // offline: the typed name stays, the pin stays where it was
    }, 600);
    return () => clearTimeout(timer);
    // Only re-run when the typed text changes, not on every pin move.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <View style={styles.wrap}>
      <TextField
        label={label}
        placeholder="Search an area, e.g. Gulshan-e-Iqbal"
        icon="location-outline"
        value={value}
        onChangeText={(text) => {
          typedRef.current = true;
          onChange(text, findArea(text) ?? { name: text, latitude: centre.latitude, longitude: centre.longitude });
        }}
        error={error}
        hint="Only this area name is shown to other members before a match."
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
        {AREAS.map((area) => {
          const active = area.name.toLowerCase() === value.trim().toLowerCase();
          return (
            <Pressable
              key={area.name}
              onPress={() => selectArea(area.name)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipLabel, active && styles.chipLabelActive]}>{area.name}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <Pressable onPress={useCurrentLocation} style={styles.currentLocation} disabled={locating}>
        {locating ? (
          <ActivityIndicator size="small" color={colors.navy} />
        ) : (
          <Ionicons name="navigate-outline" size={16} color={colors.navy} />
        )}
        <Text style={styles.currentLocationText}>
          {locating ? 'Getting your location…' : 'Use my current location'}
        </Text>
      </Pressable>

      {permissionNote ? <Text style={styles.note}>{permissionNote}</Text> : null}

      <WebMap
        latitude={centre.latitude}
        longitude={centre.longitude}
        editable
        height={280}
        hint="Tap the map or drag the pin to set the exact meeting point"
        onPin={handlePin}
      />

      {resolving ? (
        <View style={styles.resolving}>
          <ActivityIndicator size="small" color={colors.textMuted} />
          <Text style={styles.mapHint}>Looking up this point…</Text>
        </View>
      ) : (
        <Text style={styles.mapHint}>
          Map tiles are served by the SSUET RideShare server, so the map key can be changed in the
          admin dashboard without updating the app.
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  chips: { gap: spacing.sm, paddingVertical: 2 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.navy, borderColor: colors.navy },
  chipLabel: { color: colors.textMuted, ...typography.caption },
  chipLabelActive: { color: colors.textInverse, fontWeight: '600' },
  currentLocation: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  currentLocationText: { color: colors.navy, ...typography.caption, fontWeight: '700' },
  note: { color: colors.warning, ...typography.caption },
  mapHint: { flex: 1, color: colors.textMuted, ...typography.caption },
  resolving: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
