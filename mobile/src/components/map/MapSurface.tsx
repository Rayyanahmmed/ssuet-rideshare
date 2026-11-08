import { forwardRef, useImperativeHandle, useRef } from 'react';
import { StyleSheet } from 'react-native';
import { WebView } from 'react-native-webview';

/**
 * Native map surface: a WebView. The web build swaps this file for MapSurface.web.tsx
 * (an iframe) so WebMap itself stays identical on both platforms.
 */
export type MapSurfaceHandle = { inject: (js: string) => void };

type Props = {
  html: string;
  onMessage: (raw: string) => void;
  onTilesError: () => void;
};

export const MapSurface = forwardRef<MapSurfaceHandle, Props>(function MapSurface(
  { html, onMessage, onTilesError },
  ref,
) {
  const webview = useRef<WebView>(null);

  useImperativeHandle(ref, () => ({
    inject: (js: string) => webview.current?.injectJavaScript(js),
  }));

  return (
    <WebView
      ref={webview}
      originWhitelist={['*']}
      source={{ html }}
      style={styles.web}
      javaScriptEnabled
      domStorageEnabled={false}
      allowFileAccess={false}
      mixedContentMode="always"
      scrollEnabled={false}
      setSupportMultipleWindows={false}
      androidLayerType="hardware"
      onMessage={(event) => onMessage(event.nativeEvent.data)}
      onHttpError={(synthetic) => {
        if (synthetic.nativeEvent.url.includes('/maps/tiles/')) onTilesError();
      }}
    />
  );
});

const styles = StyleSheet.create({
  web: { flex: 1, backgroundColor: '#EEF1F4' },
});
