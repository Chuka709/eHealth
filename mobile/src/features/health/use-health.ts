import type { components } from "@labtrack/shared";
import { onlineManager, useMutation, useQuery } from "@tanstack/react-query";

import {
  dismissFailed,
  enqueue,
  failedWrites,
  flush,
  pendingWrites,
} from "@/features/offline/queue";
import { sendQueued } from "@/features/offline/use-local-data";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/query-client";
import { newClientId } from "@/lib/random";
import { apiError, isNetworkError } from "@/lib/use-error-text";

type S = components["schemas"];
export type HealthEvent = S["EventOut"];
export type EventFields = S["EventIn"];
export type Allergy = S["AllergyOut"];
export type AllergyFields = S["AllergyIn"];
export type Contact = S["ContactOut"];
export type ContactFields = S["ContactIn"];
export type Appointment = S["AppointmentOut"];
export type AppointmentFields = S["AppointmentIn"];
export type Question = S["QuestionOut"];
export type QuestionFields = S["QuestionIn"];
export type Vital = S["VitalOut"];
export type VitalsBody = S["VitalsIn"];

/**
 * A record kind on the API: list, create (with the form's client_id - a retried save finds
 * the stored record), replace (PUT the whole record) and delete. Lists are cached
 * (encrypted, `meta.persist`) and shown offline; writes need the network, as transplants.
 */
type Kind<TOut, TFields> = {
  key: string;
  list: (patientId: string) => Promise<TOut[]>;
  create: (patientId: string, body: TFields & { client_id: string }) => Promise<TOut>;
  update: (patientId: string, id: string, body: TFields) => Promise<TOut>;
  remove: (patientId: string, id: string) => Promise<void>;
};

const path = (patientId: string) => ({ path: { patient_id: patientId } });

async function unwrap<T>(p: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await p;
  if (data === undefined) throw apiError(error);
  return data;
}

async function removed(p: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  const { error, response } = await p;
  if (!response.ok) throw apiError(error);
}

export const EVENTS: Kind<HealthEvent, EventFields> = {
  key: "events",
  list: (p) => unwrap(api.GET("/api/v1/patients/{patient_id}/events", { params: path(p) })),
  create: (p, body) =>
    unwrap(api.POST("/api/v1/patients/{patient_id}/events", { params: path(p), body })),
  update: (p, id, body) =>
    unwrap(
      api.PUT("/api/v1/patients/{patient_id}/events/{event_id}", {
        params: { path: { patient_id: p, event_id: id } },
        body,
      }),
    ),
  remove: (p, id) =>
    removed(
      api.DELETE("/api/v1/patients/{patient_id}/events/{event_id}", {
        params: { path: { patient_id: p, event_id: id } },
      }),
    ),
};

export const ALLERGIES: Kind<Allergy, AllergyFields> = {
  key: "allergies",
  list: (p) => unwrap(api.GET("/api/v1/patients/{patient_id}/allergies", { params: path(p) })),
  create: (p, body) =>
    unwrap(api.POST("/api/v1/patients/{patient_id}/allergies", { params: path(p), body })),
  update: (p, id, body) =>
    unwrap(
      api.PUT("/api/v1/patients/{patient_id}/allergies/{allergy_id}", {
        params: { path: { patient_id: p, allergy_id: id } },
        body,
      }),
    ),
  remove: (p, id) =>
    removed(
      api.DELETE("/api/v1/patients/{patient_id}/allergies/{allergy_id}", {
        params: { path: { patient_id: p, allergy_id: id } },
      }),
    ),
};

export const CONTACTS: Kind<Contact, ContactFields> = {
  key: "contacts",
  list: (p) => unwrap(api.GET("/api/v1/patients/{patient_id}/contacts", { params: path(p) })),
  create: (p, body) =>
    unwrap(api.POST("/api/v1/patients/{patient_id}/contacts", { params: path(p), body })),
  update: (p, id, body) =>
    unwrap(
      api.PUT("/api/v1/patients/{patient_id}/contacts/{contact_id}", {
        params: { path: { patient_id: p, contact_id: id } },
        body,
      }),
    ),
  remove: (p, id) =>
    removed(
      api.DELETE("/api/v1/patients/{patient_id}/contacts/{contact_id}", {
        params: { path: { patient_id: p, contact_id: id } },
      }),
    ),
};

export const APPOINTMENTS: Kind<Appointment, AppointmentFields> = {
  key: "appointments",
  list: (p) => unwrap(api.GET("/api/v1/patients/{patient_id}/appointments", { params: path(p) })),
  create: (p, body) =>
    unwrap(api.POST("/api/v1/patients/{patient_id}/appointments", { params: path(p), body })),
  update: (p, id, body) =>
    unwrap(
      api.PUT("/api/v1/patients/{patient_id}/appointments/{appointment_id}", {
        params: { path: { patient_id: p, appointment_id: id } },
        body,
      }),
    ),
  remove: (p, id) =>
    removed(
      api.DELETE("/api/v1/patients/{patient_id}/appointments/{appointment_id}", {
        params: { path: { patient_id: p, appointment_id: id } },
      }),
    ),
};

export const QUESTIONS: Kind<Question, QuestionFields> = {
  key: "questions",
  list: (p) => unwrap(api.GET("/api/v1/patients/{patient_id}/questions", { params: path(p) })),
  create: (p, body) =>
    unwrap(api.POST("/api/v1/patients/{patient_id}/questions", { params: path(p), body })),
  update: (p, id, body) =>
    unwrap(
      api.PUT("/api/v1/patients/{patient_id}/questions/{question_id}", {
        params: { path: { patient_id: p, question_id: id } },
        body,
      }),
    ),
  remove: (p, id) =>
    removed(
      api.DELETE("/api/v1/patients/{patient_id}/questions/{question_id}", {
        params: { path: { patient_id: p, question_id: id } },
      }),
    ),
};

export const recordsKey = (kind: string, patientId: string) => [kind, patientId] as const;

export function useRecords<TOut, TFields>(
  kind: Kind<TOut, TFields>,
  patientId: string | undefined,
  { fresh = false } = {},
) {
  return useQuery({
    queryKey: recordsKey(kind.key, patientId ?? ""),
    enabled: Boolean(patientId),
    refetchOnMount: fresh ? "always" : true,
    meta: { persist: true },
    queryFn: () => kind.list(patientId ?? ""),
  });
}

const refresh = (kind: string, patientId: string) =>
  void queryClient.invalidateQueries({ queryKey: recordsKey(kind, patientId) });

const online = () => {
  if (!onlineManager.isOnline()) throw new TypeError("Network request failed");
};

export function useSaveRecord<TOut, TFields>(kind: Kind<TOut, TFields>, patientId: string) {
  return useMutation({
    networkMode: "always",
    mutationFn: ({
      id,
      body,
      clientId,
    }: {
      id: string | null;
      body: TFields;
      clientId: string;
    }) => {
      online();
      return id === null
        ? kind.create(patientId, { ...body, client_id: clientId })
        : kind.update(patientId, id, body);
    },
    onSuccess: () => {
      refresh(kind.key, patientId);
      // questions show their appointment: a changed appointment refreshes them too
      if (kind.key === "appointments") refresh("questions", patientId);
    },
  });
}

export function useDeleteRecord<TOut, TFields>(kind: Kind<TOut, TFields>, patientId: string) {
  return useMutation({
    networkMode: "always",
    mutationFn: (id: string) => {
      online();
      return kind.remove(patientId, id);
    },
    onSuccess: () => refresh(kind.key, patientId),
  });
}

// --- vitals: quick entry that works offline ------------------------------------------------

export const vitalsKey = (patientId: string) => ["vitals", patientId] as const;

/** The last 90 days of readings, newest first (cached, shown offline). */
export function useVitals(patientId: string | undefined) {
  return useQuery({
    queryKey: vitalsKey(patientId ?? ""),
    enabled: Boolean(patientId),
    meta: { persist: true },
    queryFn: async () => {
      const to = new Date(Date.now() + 60_000);
      const from = new Date(to.getTime() - 90 * 86_400_000);
      return unwrap(
        api.GET("/api/v1/patients/{patient_id}/vitals", {
          params: {
            path: { patient_id: patientId ?? "" },
            query: { from: from.toISOString(), to: to.toISOString() },
          },
        }),
      );
    },
  });
}

/**
 * A reading (one kind, or blood pressure). Online it is sent at once, so a refused number
 * ("may have been mistyped") is said right away (throws the API error); without a network it
 * waits in the encrypted offline queue (the same client_id: a retry is one reading) and a
 * later refusal is listed on the vitals screen. "full" when the queue has no room.
 */
export async function recordVitals(
  patientId: string,
  items: { kind: VitalsBody["items"][number]["kind"]; value: string }[],
  note: string | null,
  epoch: number,
): Promise<"saved" | "queued" | "full"> {
  const clientId = newClientId();
  const body: VitalsBody = {
    client_id: clientId,
    measured_at: new Date().toISOString(),
    note,
    items,
  };
  try {
    const { data, error } = await api.POST("/api/v1/patients/{patient_id}/vitals", {
      params: { path: { patient_id: patientId } },
      body,
    });
    if (data) {
      void queryClient.invalidateQueries({ queryKey: vitalsKey(patientId) });
      return "saved";
    }
    throw apiError(error);
  } catch (exc) {
    if (!isNetworkError(exc)) throw exc; // the server answered (or a bug): say why
  }
  const queued = await enqueue(
    { id: clientId, method: "POST", path: `/api/v1/patients/${patientId}/vitals`, body },
    epoch,
  );
  if (!queued) return "full";
  void flush(sendQueued)
    .catch(() => undefined)
    .finally(() => {
      void queryClient.invalidateQueries({ queryKey: vitalsKey(patientId) });
      void queryClient.invalidateQueries({ queryKey: ["queue", "vitals", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["queue", "failed-vitals", patientId] });
    });
  void queryClient.invalidateQueries({ queryKey: ["queue", "vitals", patientId] });
  return "queued";
}

/** Readings the server refused after waiting offline: shown until the user has seen them. */
export function useFailedVitals(patientId: string | undefined) {
  return useQuery({
    queryKey: ["queue", "failed-vitals", patientId ?? ""],
    enabled: Boolean(patientId),
    networkMode: "always",
    queryFn: async () => {
      const path = `/api/v1/patients/${patientId}/vitals`;
      return (await failedWrites()).filter((w) => w.path === path);
    },
  });
}

export async function dismissFailedVital(patientId: string, id: string): Promise<void> {
  await dismissFailed(id);
  void queryClient.invalidateQueries({ queryKey: ["queue", "failed-vitals", patientId] });
}

/** Readings waiting in the offline queue (shown as "waiting to be sent", never twice). */
export function usePendingVitals(patientId: string | undefined) {
  return useQuery({
    queryKey: ["queue", "vitals", patientId ?? ""],
    enabled: Boolean(patientId),
    networkMode: "always",
    queryFn: async () => {
      const path = `/api/v1/patients/${patientId}/vitals`;
      return (await pendingWrites()).filter((w) => w.path === path);
    },
  });
}

export function useDeleteVital(patientId: string) {
  return useMutation({
    mutationFn: (id: string) =>
      removed(
        api.DELETE("/api/v1/patients/{patient_id}/vitals/{vital_id}", {
          params: { path: { patient_id: patientId, vital_id: id } },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: vitalsKey(patientId) }),
  });
}
