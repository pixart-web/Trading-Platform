import { z } from "zod";
const money = z.string().regex(/^-?\d+(\.\d+)?([eE][+-]?\d+)?$/).refine(value => Number.isFinite(Number(value)), "Decimal inválido");
const timestamp = z.iso.datetime({ offset: true });
export const paperView = z.object({
  mode: z.literal("PAPER"), live_ready: z.literal(false),
  observed_at: timestamp, ready: z.boolean(), readiness_reason: z.string().nullable(),
  config: z.object({mode: z.literal("PAPER")}),
  state: z.object({
    mode: z.literal("PAPER"), account_id: z.uuid(), revision: z.number().int().nonnegative(),
    origin: z.enum(["REAL", "SYNTHETIC"]), market_id: z.string(), quote_currency: z.string(),
    at: timestamp, status: z.enum(["WAITING_DATA", "ACTIVE", "SUSPENDED", "HALTED", "CLOSED"]),
    reason: z.string().nullable(), last_price: money.nullable(), last_close: timestamp.nullable(),
    portfolio: z.object({cash: money, quantity: money, equity: money, reserved_cash: money}),
    realized_pnl: money, unrealized_pnl: money.nullable(), total_fees: money,
    pending: z.array(z.object({client_id: z.string()})),
    fills: z.array(z.object({client_id: z.string(), at: timestamp, quantity: money, price: money, fee: money})),
    orders: z.array(z.object({client_id: z.string(), at: timestamp, state: z.string(), reason: z.string()})),
    live_ready: z.literal(false), profitability_claim: z.literal(false),
  }),
});
export const paperAccounts = z.array(paperView).max(100);
export type PaperView = z.infer<typeof paperView>;
