/**
 * Karachi area centroids.
 *
 * Used as a sensible default pickup point when the member picks an area but does
 * not (or cannot) drop a pin on the map — e.g. while offline or if an administrator
 * has disabled maps (§13). Coordinates are neighbourhood centres, never home addresses.
 */
export type AreaPoint = { name: string; latitude: number; longitude: number };

export const AREAS: AreaPoint[] = [
  { name: 'Gulshan-e-Iqbal', latitude: 24.92, longitude: 67.09 },
  { name: 'Gulistan-e-Johar', latitude: 24.92, longitude: 67.14 },
  { name: 'North Nazimabad', latitude: 24.94, longitude: 67.04 },
  { name: 'Federal B Area', latitude: 24.93, longitude: 67.07 },
  { name: 'PECHS', latitude: 24.87, longitude: 67.06 },
  { name: 'Clifton', latitude: 24.81, longitude: 67.03 },
  { name: 'Saddar', latitude: 24.86, longitude: 67.01 },
  { name: 'Scheme 33', latitude: 24.95, longitude: 67.1 },
  { name: 'Malir', latitude: 24.89, longitude: 67.2 },
  { name: 'Korangi', latitude: 24.84, longitude: 67.12 },
  { name: 'Gulberg', latitude: 24.92, longitude: 67.06 },
  { name: 'Liaquatabad', latitude: 24.91, longitude: 67.06 },
  { name: 'Gulshan-e-Hadeed', latitude: 24.87, longitude: 67.33 },
  { name: 'Bahria Town Karachi', latitude: 25.0, longitude: 67.3 },
];

export const SSUET: AreaPoint = {
  name: 'SSUET, University Road, Karachi',
  latitude: 24.9372,
  longitude: 67.1138,
};

export function findArea(name: string): AreaPoint | undefined {
  const needle = name.trim().toLowerCase();
  return AREAS.find((area) => area.name.toLowerCase() === needle);
}
