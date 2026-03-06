import { describe, it, expect } from "vitest";
import { estimateCost } from "@/lib/cost";

describe("estimateCost", () => {
  it("returns cost for known model", () => {
    const cost = estimateCost("claude-sonnet-4-6", 1_000_000, 1_000_000);
    expect(cost).toBe(3.0 + 15.0);
  });

  it("returns zero for unknown model", () => {
    const cost = estimateCost("unknown-model", 1000, 1000);
    expect(cost).toBe(0);
  });

  it("returns zero for zero tokens", () => {
    const cost = estimateCost("claude-sonnet-4-6", 0, 0);
    expect(cost).toBe(0);
  });

  it("handles input only", () => {
    const cost = estimateCost("claude-sonnet-4-6", 1_000_000, 0);
    expect(cost).toBe(3.0);
  });

  it("handles output only", () => {
    const cost = estimateCost("claude-sonnet-4-6", 0, 1_000_000);
    expect(cost).toBe(15.0);
  });

  it("handles fractional tokens", () => {
    const cost = estimateCost("claude-sonnet-4-6", 500_000, 500_000);
    expect(cost).toBeCloseTo(1.5 + 7.5, 5);
  });

  it("computes correct cost for all pricing models", () => {
    const models = [
      { model: "claude-sonnet-4-6", inPer: 3.0, outPer: 15.0 },
      { model: "claude-haiku-4-5", inPer: 0.25, outPer: 1.25 },
      { model: "gpt-5.2", inPer: 5.0, outPer: 15.0 },
      { model: "gpt-4o-mini", inPer: 0.15, outPer: 0.6 },
    ];
    for (const { model, inPer, outPer } of models) {
      const cost = estimateCost(model, 1_000_000, 1_000_000);
      expect(cost).toBeCloseTo(inPer + outPer, 5);
    }
  });

  it("returns zero for empty string model", () => {
    const cost = estimateCost("", 1000, 1000);
    expect(cost).toBe(0);
  });
});
