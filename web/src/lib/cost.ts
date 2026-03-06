import pricing from "./pricing.json";

const pricingMap = pricing as Record<string, { input_per_mtok: number; output_per_mtok: number }>;

export function estimateCost(model: string, tokensIn: number, tokensOut: number): number {
  const p = pricingMap[model];
  if (!p) return 0;
  return (tokensIn / 1_000_000) * p.input_per_mtok + (tokensOut / 1_000_000) * p.output_per_mtok;
}
