import { rupees } from "@/lib/format";

export type Line = { id: number; menu_item_id: number; item_name: string; variant_name: string; addons: { id: number; name: string }[]; quantity: number; unit_price_paise: number; line_total_paise: number; instructions: string };
export type Bill = { lines: { name: string; detail: string; quantity: number; unit_price: number; total: number }[]; subtotal: number; discount: number; discount_name: string;
  charges: { name: string; amount: number }[]; taxes: { rate_bp: number; taxable: number; cgst: number; sgst: number; tax: number; on?: string }[]; tax_total: number; total: number; prices_include_tax: boolean; amount_due_now?: number };
export type Order = { ref: string; status: string; channel: string; order_type: string; scheduled_for: string | null; special_instructions: string; bill: Bill;
  total_paise: number; amount_due_paise: number; amount_paid_paise: number; estimate_minutes: number | null; estimated_ready_at: string | null; invoice_number: string | null;
  created_at: string; cancel_reason: string; customer: { name: string; phone: string }; items: Line[];
  payments: { ref: string; status: string; amount_paise: number; short_url: string; refunded_paise: number }[]; quote?: { estimate_minutes: number; meets_target: boolean; target_minutes: number; reasons: string[] } };

export function BillView({ bill }: { bill: Bill }) {
  return (
    <table className="table">
      <tbody>
        {bill.lines.map((l, i) => <tr key={i}><td>{l.quantity} × {l.name}{l.detail && <div className="text-xs text-stone-500">{l.detail}</div>}</td><td className="text-right">{rupees(l.total)}</td></tr>)}
        <tr><td>Subtotal</td><td className="text-right">{rupees(bill.subtotal)}</td></tr>
        {bill.discount > 0 && <tr><td>Discount ({bill.discount_name})</td><td className="text-right">-{rupees(bill.discount)}</td></tr>}
        {bill.charges.map((c) => <tr key={c.name}><td>{c.name}</td><td className="text-right">{rupees(c.amount)}</td></tr>)}
        {bill.taxes.map((t, i) => <tr key={i}><td className="text-xs">CGST {t.rate_bp / 200}% + SGST {t.rate_bp / 200}%{t.on === "charges" ? " on charges" : ""} on {rupees(t.taxable)}{bill.prices_include_tax && t.on !== "charges" ? " (included)" : ""}</td><td className="text-right text-xs">{rupees(t.cgst)} + {rupees(t.sgst)}</td></tr>)}
        <tr className="font-semibold"><td>Total</td><td className="text-right">{rupees(bill.total)}</td></tr>
        {bill.amount_due_now !== undefined && bill.amount_due_now !== bill.total && <tr><td>Due online now</td><td className="text-right">{rupees(bill.amount_due_now)}</td></tr>}
      </tbody>
    </table>
  );
}

