import { useLocalSearchParams } from "expo-router";

import { QuestionEditor } from "@/features/health/forms";

export default function QuestionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <QuestionEditor id={id} />;
}
