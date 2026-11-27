import { useTranslations } from "use-intl";

import { questionRow } from "@/features/health/forms";
import { RecordList } from "@/features/health/record-screens";
import { QUESTIONS } from "@/features/health/use-health";

export default function QuestionsScreen() {
  const t = useTranslations("app.health");
  return (
    <RecordList
      kind={QUESTIONS as never}
      route="/questions"
      row={questionRow(t as (k: string) => string) as never}
      addLabel={t("question.new")}
    />
  );
}
