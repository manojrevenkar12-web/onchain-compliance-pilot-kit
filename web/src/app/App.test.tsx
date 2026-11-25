import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixture from "../test/report.fixture.json";
import { App } from "./App";

function serve(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok, status, json: () => Promise.resolve(body) })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("pilot room", () => {
  it("shows a loading state, then the scorecard", async () => {
    serve(fixture);
    render(<App />);
    expect(screen.getByRole("status", { name: "Loading the pilot report" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("success criteria met");
    expect(screen.getAllByText(/Agreed in discovery/).length).toBe(5);
  });

  it("shows an error with a retry", async () => {
    serve({}, false, 500);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 500");
    serve(fixture);
    await userEvent.click(screen.getByRole("button", { name: "Load again" }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("refuses a report of the wrong shape", async () => {
    serve({ dev: { prospects: {} } });
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("not in the expected shape");
  });

  it("switches prospect", async () => {
    serve(fixture);
    render(<App />);
    const nav = await screen.findByRole("navigation", { name: "Prospect" });
    const tabs = within(nav).getAllByRole("button");
    expect(tabs.length).toBe(Object.keys(fixture.dev.prospects).length);
    await userEvent.click(tabs[1]!);
    expect(tabs[1]).toHaveAttribute("aria-current", "page");
    const second = Object.values(fixture.dev.prospects)[1]!.discovery.name.replace(" (fictional)", "");
    expect(await screen.findByRole("heading", { level: 1, name: new RegExp(second) })).toBeInTheDocument();
  });

  it("lists the webhook lab and the gates", async () => {
    serve(fixture);
    render(<App />);
    expect(await screen.findByText("Without the signature check")).toBeInTheDocument();
    expect(screen.getByText(/gates pass/)).toBeInTheDocument();
  });
});
