import { z } from 'zod';
import type { components } from './schema';
import { api, ApiError, newIdempotencyKey } from './client';
import { queryClient } from './query-client';

export type Invoice = components['schemas']['InvoiceView'];
export type InvoiceDetail = components['schemas']['InvoiceDetail'];
export type Run = components['schemas']['RunView'];
export type Statement = components['schemas']['StatementView'];
export type ConfirmationRequest = components['schemas']['ConfirmationRequest'];
export type MemberSettlement = components['schemas']['MemberSettlement'];
export type SettlementDetail = components['schemas']['SettlementDetail'];
export type LedgerCheck = components['schemas']['LedgerCheck'];
export type SavingsSummary = components['schemas']['SavingsSummary'];
export type SavingsItem = components['schemas']['SavingsItem'];
export type Estimate = components['schemas']['Estimate'];
export type EstimateRequest = components['schemas']['EstimateRequest'];
export type NetworkView = components['schemas']['NetworkView'];
export type GraphNode = components['schemas']['GraphNode'];
export type GraphEdge = components['schemas']['GraphEdge'];
export type CaseView = components['schemas']['CaseView'];
export type AuditView = components['schemas']['AuditView'];
export type NotificationList = components['schemas']['NotificationList'];
export const invoiceFormSchema = z.object({
	invoice_number: z.string().trim().min(1).max(64),
	issuer_tax_id: z.string().trim().min(1),
	payer_tax_id: z.string().trim().min(1),
	currency: z.enum(['EUR', 'USD', 'GBP', 'HUF', 'CNY']),
	amount: z
		.string()
		.regex(/^\d+(\.\d{1,2})?$/, 'Use a positive amount with at most two decimal places'),
	outstanding: z.string().regex(/^(\d+(\.\d{1,2})?)?$/),
	issue_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
	due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
});
export async function refreshMesh() {
	await queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'mesh' });
}
export function activeRun(status?: string) {
	return !!status && !['COMMITTED', 'ABORTED', 'FALLBACK_GROSS'].includes(status);
}
export async function uploadCsv(file: File) {
	let response: Response;
	try {
		response = await fetch('/v1/invoices/uploads', {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'Content-Type': 'text/csv',
				'X-Requested-With': 'mesh-web',
				'Idempotency-Key': newIdempotencyKey()
			},
			body: file
		});
	} catch (cause) {
		throw ApiError.network(cause);
	}
	const data = await response.json();
	if (!response.ok) throw ApiError.fromResponse(response, data);
	return data as components['schemas']['UploadResult'];
}
export { api };
