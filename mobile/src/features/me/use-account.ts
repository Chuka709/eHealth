import type { components } from "@labtrack/shared";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef } from "react";

import { refreshSession, wipeLocal } from "@/features/auth/session";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { apiError } from "@/lib/use-error-text";

export type AdminAction = components["schemas"]["AdminActionOut"];
export type AppNotification = components["schemas"]["NotificationOut"];

const actionsKey = ["me", "admin-actions"] as const;

/**
 * The response to a report or deletion may be lost after the server already ended every
 * session. A refresh then answers why (auth.account_reported / auth.deletion_pending) and the
 * device shows that notice instead of leaving the user unaware.
 */
function checkWhetherItWentThrough(error: unknown): void {
  if (error instanceof TypeError) void refreshSession();
}

const notificationsKey = ["me", "notifications"] as const;

/** What admins did on this account: when, what, which role — never who (docs/04 §1). */
export function useAdminActions() {
  return useQuery({
    queryKey: actionsKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/admin-actions");
      if (!data) throw apiError(error);
      return data;
    },
  });
}

/** Unread notices about admin changes to the account (shown on Home with "Би хүсээгүй"). */
export function useAdminNotices() {
  return useQuery({
    queryKey: notificationsKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/me/notifications");
      if (!data) throw apiError(error);
      return data.filter(
        (n) => n.read_at === null && (n.kind === "admin_reset" || n.kind === "admin_action"),
      );
    },
  });
}

/** Marks exactly the shown notices read (all of them, or the error is shown). */
export function useMarkNoticeRead() {
  return useMutation({
    mutationFn: async (ids: number[]) => {
      await Promise.all(
        ids.map(async (id) => {
          const { error, response } = await api.POST(
            "/api/v1/me/notifications/{notification_id}/read",
            { params: { path: { notification_id: id } } },
          );
          if (!response.ok) throw apiError(error);
        }),
      );
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: notificationsKey }),
  });
}

/**
 * "Би хүсээгүй" (docs/04 §1 step 5c): the server locks the account and ends every session;
 * the device is then wiped and shows a notice with whom to call.
 */
export function useReportUnwantedAdminAction() {
  return useMutation({
    onError: checkWhetherItWentThrough,
    mutationFn: async () => {
      const { error, response } = await api.POST("/api/v1/me/report-unwanted-admin-action");
      if (!response.ok) throw apiError(error);
      await wipeLocal({ kind: "reported" });
    },
  });
}

/**
 * Account deletion (docs/04 §1): password re-checked by the server, then 202 with the date it
 * becomes final; every session ends. The password goes through a ref, not mutation variables.
 */
export function useDeleteAccount() {
  const password = useRef<string | null>(null);
  const mutation = useMutation({
    gcTime: 0,
    onError: checkWhetherItWentThrough,
    mutationFn: async () => {
      const value = password.current;
      password.current = null;
      if (!value) throw new Error("no input");
      const { data, error } = await api.POST("/api/v1/me/delete", { body: { password: value } });
      if (!data) throw apiError(error);
      await wipeLocal({ kind: "deleted", scheduledFor: data.scheduled_for });
    },
  });
  const submit = (value: string, options?: Parameters<typeof mutation.mutate>[1]) => {
    if (mutation.isPending) return;
    password.current = value;
    mutation.mutate(undefined, options);
  };
  return { ...mutation, submit };
}
