export type InvoiceStatus =
  | "PENDING"
  | "PAID"
  | "CANCELLED"
  | "EXPIRED";

export type PaymentStatus =
  | "PENDING_DEPOSIT"
  | "KNOWN_DEPOSIT_TX"
  | "INCOMPLETE_DEPOSIT"
  | "PROCESSING"
  | "SUCCESS"
  | "REFUNDED"
  | "FAILED";

export interface InvoiceItem {
  id?: number;
  description: string;
  quantity: string | number;
  unit_price: string | number;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  freelancer_id?: string;
  client_name: string;
  client_email?: string;
  total: string;
  currency: string;
  status: InvoiceStatus;
  due_date?: string | null;
  created_at?: string;
  items: InvoiceItem[];
  payment_url?: string;
}

export interface Client {
  id: string;
  name: string;
  email: string;
  company?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface PaymentAttempt {
  id: string;
  payment_attempt_id?: string;
  invoice_id: string;
  invoice_number?: string;
  client_name?: string;
  status: PaymentStatus;
  deposit_address?: string;
  deposit_memo?: string | null;
  source_asset?: string;
  destination_asset?: string;
  expected_amount?: string;
  received_amount?: string | null;
  created_at?: string;
  transactions?: Transaction[];
}

export interface Transaction {
  id: string;
  chain?: string;
  tx_hash: string;
  transaction_type: string;
  amount?: string | null;
  explorer_url?: string | null;
  created_at?: string;
}

export interface DashboardStats {
  total_invoiced: number;
  total_paid: number;
  pending_amount: number;
  invoice_count: number;
  paid_count: number;
  pending_count: number;
}