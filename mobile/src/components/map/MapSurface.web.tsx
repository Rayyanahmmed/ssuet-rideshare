import { createElement, forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { StyleSheet, View } from 'react-native';

/**
 * Web map surface: the same map HTML inside an iframe.
 *
 * The HTML talks to `window.ReactNativeWebView.postMessage`, which does not exist in a
 * browser. A tiny shim (prepended to the document) forwards those calls to the parent page,
 * and this component only accepts messages that come from its own iframe.
 */
export type MapSurfaceHandle = { inject: (js: string) => void };

type Props = {
  html: string;
  onMessage: (raw: string) => void;
  onTilesError: () => void;
};

const SHIM =
  '<script>window.ReactNativeWebView={postMessage:function(t){' +
  'window.parent.postMessage({ssuetMap:true,data:String(t)},"*");}};</script>';

export const MapSurface = forwardRef<MapSurfaceHandle, Props>(function MapSurface(
  { html, onMessage },
  ref,
) {
  const frame = useRef<HTMLIFrameElement | null>(null);

  useImperativeHandle(ref, () => ({
    inject: (js: string) => {
      try {
        const win = frame.current?.contentWindow as unknown as { eval: (code: string) => unknown } | null;
        win?.eval(js);
      } catch {
        // the map document is not ready yet; the next call will succeed
      }
    },
  }));

  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return;
      const payload = event.data as { ssuetMap?: boolean; data?: string } | null;
      if (payload?.ssuetMap && typeof payload.data === 'string') onMessage(payload.data);
    };
    window.addEventListener('message', listener);
    return () => window.removeEventListener('message', listener);
  }, [onMessage]);

  return (
    <View style={styles.box}>
      {createElement('iframe', {
        ref: frame,
        srcDoc: SHIM + html,
        title: 'Map',
        style: { border: 0, width: '100%', height: '100%' },
      })}
    </View>
  );
});

const styles = StyleSheet.create({
  box: { flex: 1, backgroundColor: '#EEF1F4' },
});
