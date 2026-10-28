import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { I18nProvider } from "@/lib/i18n";

import { HealthStatus } from "./health-status";

const mockFetch = jest.fn<Promise<Response>, [Request]>();

beforeEach(() => {
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

function wrap(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Number.POSITIVE_INFINITY } },
  });
  return (
    <I18nProvider>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nProvider>
  );
}

const ok = () =>
  new Response(JSON.stringify({ status: "ok" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

test("shows connected state with text, not colour only", async () => {
  mockFetch.mockResolvedValue(ok());
  await render(wrap(<HealthStatus />));
  expect(await screen.findByText("Сервертэй холбогдлоо")).toBeOnTheScreen();
  expect(screen.getByLabelText("Сервертэй холбогдлоо")).toBeOnTheScreen();
});

test("shows a calm error and a retry button that refetches", async () => {
  mockFetch.mockRejectedValueOnce(new TypeError("Network request failed"));
  await render(wrap(<HealthStatus />));
  const retry = await screen.findByRole("button", { name: "Дахин оролдох" });
  expect(screen.getByText(/Сервертэй холбогдож чадсангүй/)).toBeOnTheScreen();

  mockFetch.mockResolvedValueOnce(ok());
  await fireEvent.press(retry);
  expect(await screen.findByText("Сервертэй холбогдлоо")).toBeOnTheScreen();
});
