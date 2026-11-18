import { fontSize, space, emergencyWallpaper as wallpaper } from "@labtrack/shared";
import { type ComponentRef, type RefObject, useRef } from "react";
import { PixelRatio, StyleSheet, View } from "react-native";
import { captureRef } from "react-native-view-shot";
import { Text } from "@/components/app-text";

import type { Locale } from "@/lib/i18n";

import { type CardFields, cardText } from "./card-text";
import { type ShareResult, shareFile, startExport, writeForSharing } from "./export-files";
import type { EmergencyCard } from "./snapshot";

/**
 * The lock-screen wallpaper (docs/08, H17): the card as an image for the phone's own lock
 * screen, which no app can draw on. Anyone who picks up the phone sees it, so the name and
 * date of birth are off unless the user turns them on (user decision 2.7 (a)). The top part
 * stays empty for the clock. The preview on screen is exactly what is saved, and it reports
 * when not everything fits (the wallet card then carries the rest).
 */

export type WallpaperView = ComponentRef<typeof View>;

export function Wallpaper({
  card,
  locale,
  fields,
  onFit,
  viewRef,
  label,
}: {
  card: EmergencyCard;
  locale: Locale;
  fields: CardFields;
  onFit: (fits: boolean) => void;
  viewRef: RefObject<WallpaperView | null>;
  /** spoken before the content: what this is (an image preview) */
  label: string;
}) {
  const text = cardText(card, locale, fields);
  // both heights from their own layouts, compared whenever either changes
  const heights = useRef({ room: 0, content: 0 });
  const measure = (part: "room" | "content", height: number) => {
    heights.current[part] = height;
    const { room, content } = heights.current;
    if (room > 0 && content > 0) onFit(content <= room);
  };
  return (
    <View
      ref={viewRef}
      collapsable={false} // Android: keep a native view to capture
      style={styles.frame}
      accessible
      accessibilityRole="image"
      accessibilityLabel={[
        label,
        text.title,
        ...[...text.front, ...text.back].flatMap((s) => s.lines),
      ].join(". ")}
    >
      <View style={styles.clock} />
      <View
        style={styles.body}
        onLayout={(event) => measure("room", event.nativeEvent.layout.height)}
      >
        <View onLayout={(event) => measure("content", event.nativeEvent.layout.height)}>
          {/* fixed sizes: the saved image is the same whatever the phone's text size */}
          <Text allowFontScaling={false} style={styles.title}>
            🆘 {text.title}
          </Text>
          {[...text.front, ...text.back].map((section, i) => (
            // a fixed, generated list: the order never changes while shown
            // biome-ignore lint/suspicious/noArrayIndexKey: sections have no identity of their own
            <View key={i} style={styles.section}>
              {section.heading && (
                <Text allowFontScaling={false} style={styles.heading}>
                  {section.heading}
                </Text>
              )}
              {section.lines.map((line, j) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: as above
                <Text key={j} allowFontScaling={false} style={styles.line}>
                  {line}
                </Text>
              ))}
            </View>
          ))}
        </View>
      </View>
    </View>
  );
}

/**
 * Captures the preview as a phone-sized PNG and opens the share sheet (Save Image). Taken as
 * base64 and written straight into the export folder: no temporary file elsewhere (Android may
 * put a view-shot tmpfile in external cache).
 */
export async function shareWallpaper(view: WallpaperView): Promise<ShareResult> {
  const ticket = startExport();
  const ratio = PixelRatio.get();
  const base64 = await captureRef(view, {
    format: "png",
    quality: 1,
    result: "base64",
    width: 1170 / ratio,
    height: 2532 / ratio,
  });
  const file = await writeForSharing(ticket, decodeBase64(base64), "emergency-wallpaper.png");
  return shareFile(ticket, file, "image/png");
}

function decodeBase64(text: string): Uint8Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

const styles = StyleSheet.create({
  frame: {
    width: "70%", // the share button stays near on screen
    alignSelf: "center",
    aspectRatio: 1170 / 2532,
    backgroundColor: wallpaper.background,
    padding: space.md,
    overflow: "hidden",
  },
  clock: { flex: 30 }, // the lock screen's clock and date
  body: { flex: 70, overflow: "hidden" },
  title: { color: wallpaper.accent, fontSize: fontSize.body, fontWeight: "700" },
  section: { marginTop: space.xs },
  heading: { color: wallpaper.accent, fontSize: fontSize.caption, fontWeight: "700" },
  line: { color: wallpaper.text, fontSize: fontSize.caption, lineHeight: fontSize.caption * 1.3 },
});
