import { qrColors } from "@labtrack/shared";
import { create } from "qrcode";
import { useMemo } from "react";
import { View } from "react-native";
import Svg, { Path, Rect } from "react-native-svg";

/**
 * A QR code drawn on the phone (nothing leaves it to be drawn): black modules on white with a
 * 4-module quiet zone, whatever the app theme, so every camera reads it. Medium error
 * correction. The label tells a screen reader what it is; the link is also shown as text.
 */
export function QrCode({
  value,
  size,
  label,
  testID,
}: {
  value: string;
  size: number;
  label: string;
  testID?: string;
}) {
  const { count, path } = useMemo(() => {
    const { modules } = create(value, { errorCorrectionLevel: "M" });
    const n = modules.size;
    let d = "";
    for (let y = 0; y < n; y += 1) {
      for (let x = 0; x < n; x += 1) {
        if (modules.get(y, x)) d += `M${x + 4} ${y + 4}h1v1h-1z`;
      }
    }
    return { count: n + 8, path: d };
  }, [value]);
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={label} testID={testID}>
      <Svg width={size} height={size} viewBox={`0 0 ${count} ${count}`}>
        <Rect width={count} height={count} fill={qrColors.light} />
        <Path d={path} fill={qrColors.dark} />
      </Svg>
    </View>
  );
}
