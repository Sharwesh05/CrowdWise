import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import LoginPage from "@/app/login/page";
import { ToastProvider } from "@/components/ui";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/login",
}));

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

describe("Login page", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders accessible, labelled fields", () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("sends credentials to the API and routes to the right dashboard", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          user: { id: 1, name: "Ravi", email: "r@example.com", role: "CONTRIBUTOR" },
          csrf_token: "token",
          message: "Signed in.",
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/email/i), "r@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "Demo@12345");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/login");
    // Cookies must travel with every request; the session is HTTP-only.
    expect(options.credentials).toBe("include");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/contributor/dashboard"));
  });

  it("surfaces the API error message instead of a generic failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () =>
          JSON.stringify({
            error: { code: "unauthenticated", message: "Incorrect email or password." },
          }),
      }),
    );

    renderWithProviders(<LoginPage />);
    await userEvent.type(screen.getByLabelText(/email/i), "r@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/incorrect email or password/i)).toBeInTheDocument();
  });
});
