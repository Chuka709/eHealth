import { useEffect } from "react";

import { setWizardActive } from "@/features/records/onboarding-store";
import { TransplantWizard } from "@/features/records/transplant-wizard";

/** First sign-in: the transplant wizard (skippable) before the app (docs/08 "Анх нэвтрэх"). */
export default function OnboardingTransplantScreen() {
  useEffect(() => {
    setWizardActive(true);
    return () => setWizardActive(false);
  }, []);
  return <TransplantWizard canSkip safeTop onDone={() => setWizardActive(false)} />;
}
