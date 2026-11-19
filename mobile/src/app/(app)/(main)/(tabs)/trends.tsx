import { useRouter } from "expo-router";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { NavGroup, NavRow } from "@/components/nav-row";
import { Screen } from "@/components/screen";
import { LoadingView, RetryView } from "@/components/state-view";
import { Paragraph } from "@/components/text";
import { TextField } from "@/components/text-field";
import { useRecordProfile } from "@/features/health/record-screens";
import { ProfileSwitcher } from "@/features/records/profile-switcher";
import { useTested } from "@/features/trends/use-trends";
import { formatDate } from "@/lib/dates";
import { useErrorText } from "@/lib/use-error-text";

/**
 * Trends (docs/08 "Хандлага"): the tests the profile has confirmed results of, most recent
 * first, with a search; a row opens the test's chart. Drafts are never listed (rule 4).
 */
export default function TrendsScreen() {
  const t = useTranslations("app.trends");
  const router = useRouter();
  const errorText = useErrorText();
  const { own } = useRecordProfile();
  const tested = useTested(own?.id);
  const [query, setQuery] = useState("");

  if (tested.isPending && own) return <LoadingView />;
  if (tested.isError) {
    return <RetryView text={errorText(tested.error)} onRetry={() => tested.refetch()} />;
  }
  const needle = query.trim().toLocaleLowerCase();
  const rows = (tested.data ?? []).filter(
    (r) =>
      needle === "" ||
      r.name_mn.toLocaleLowerCase().includes(needle) ||
      r.name_en.toLocaleLowerCase().includes(needle) ||
      r.test_code.toLocaleLowerCase().includes(needle),
  );
  return (
    <Screen testID="trends-screen">
      <ProfileSwitcher />
      {(tested.data ?? []).length === 0 ? (
        <Paragraph muted>{t("empty")}</Paragraph>
      ) : (
        <>
          <TextField
            label={t("search")}
            value={query}
            onChangeText={setQuery}
            autoCorrect={false}
            testID="trends-search"
          />
          {rows.length === 0 ? (
            <Paragraph muted>{t("noMatch")}</Paragraph>
          ) : (
            <NavGroup>
              {rows.map((r) => (
                <NavRow
                  key={r.test_code}
                  label={r.name_mn}
                  hint={t("count", { count: r.results, date: formatDate(r.latest) })}
                  onPress={() => router.push(`/trends/${r.test_code}`)}
                  testID={`trend-${r.test_code}`}
                />
              ))}
            </NavGroup>
          )}
        </>
      )}
    </Screen>
  );
}
