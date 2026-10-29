import * as Linking from "expo-linking";
import { useTranslations } from "use-intl";

import { Button } from "@/components/button";
import { supportPhone, supportPhoneUrl } from "@/lib/support";

/** "Call {phone}" button for the organisation's support line (hidden when not configured). */
export function CallSupportButton({ variant }: { variant?: "primary" | "secondary" }) {
  const t = useTranslations("app.common");
  if (!supportPhone || !supportPhoneUrl) return null;
  const url = supportPhoneUrl;
  return (
    <Button
      variant={variant}
      label={t("call", { phone: supportPhone })}
      onPress={() => {
        void Linking.openURL(url).catch(() => undefined);
      }}
    />
  );
}
