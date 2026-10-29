import { Redirect } from "expo-router";

import { useSession } from "@/features/auth/use-session";

/** Anchor route: sends "/" (launch, or a guard that just flipped) to the right group. */
export default function Index() {
  const status = useSession();
  if (status === "signedIn") return <Redirect href="/home" />;
  return <Redirect href={status === "adminReset" ? "/admin-reset" : "/welcome"} />;
}
