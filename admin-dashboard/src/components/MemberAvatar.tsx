import { useEffect, useState } from 'react';
import { fetchProfilePhotoUrl, withThumbVariant } from '@/lib/media';

/**
 * A member's face, or their initials when they have not uploaded one (§5, Phase 13).
 *
 * Used in the member list and the dossier drawer. Load failures are silent — a missing
 * or unreadable photo is not an error worth interrupting an administrator's work for,
 * the initials stand in.
 */
function initials(name: string): string {
  return (
    name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? '')
      .join('') || 'S'
  );
}

export function MemberAvatar({
  name,
  photoPath,
  size = 36,
}: {
  name: string;
  photoPath?: string | null;
  size?: number;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSrc(null);
    setFailed(false);
    if (!photoPath) return () => undefined;

    // A 36 px row avatar does not need the 512 px original (§14).
    fetchProfilePhotoUrl(size <= 40 ? withThumbVariant(photoPath) : photoPath)
      .then((url) => {
        if (!cancelled) setSrc(url);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [photoPath, size]);

  const style = { width: size, height: size, borderRadius: size / 2 };

  if (src && !failed) {
    return (
      <img
        src={src}
        alt={`${name} profile photo`}
        style={style}
        className="shrink-0 object-cover"
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <span
      style={{ ...style, fontSize: Math.round(size * 0.36) }}
      className="flex shrink-0 items-center justify-center bg-navy font-semibold text-white"
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
