<script lang="ts">
	import { api, refreshMesh, type Invoice, type ConfirmationRequest } from '$lib/api/mesh';
	import { unwrap } from '$lib/api/client';
	import Button from './Button.svelte';
	let { invoice, writable = true }: { invoice: Invoice; writable?: boolean } = $props();
	let mode = $state<'DISPUTE' | 'CORRECT' | null>(null);
	let reason = $state('WRONG_AMOUNT');
	let amount = $state('');
	let outstanding = $state('');
	let due = $state('');
	let busy = $state(false);
	let error = $state('');
	let success = $state('');
	async function decide(decision: ConfirmationRequest['decision']) {
		busy = true;
		error = '';
		success = '';
		try {
			const body: ConfirmationRequest = { decision, version: invoice.current_version };
			if (decision === 'DISPUTE') body.reason_code = reason;
			if (decision === 'CORRECT') {
				body.corrected_fields = {
					...(amount ? { amount } : {}),
					...(outstanding ? { outstanding } : {}),
					...(due ? { due_date: due } : {})
				};
			}
			await unwrap(
				api.POST('/v1/invoices/{invoice_id}/confirmations', {
					params: { path: { invoice_id: invoice.id } },
					body
				})
			);
			success =
				decision === 'CONFIRM'
					? 'Confirmed.'
					: decision === 'DISPUTE'
						? 'Disputed.'
						: 'New version created. Both parties must confirm the new terms.';
			mode = null;
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'The decision could not be saved.';
		} finally {
			busy = false;
		}
	}
</script>

{#if writable && ['PENDING_CONFIRMATION', 'CONFIRMED', 'DISPUTED'].includes(invoice.status)}
	<div class="flex flex-col gap-4">
		<div class="flex flex-wrap gap-3">
			{#if invoice.needs_confirmation}<Button loading={busy} onclick={() => decide('CONFIRM')}
					>Confirm terms</Button
				>{/if}
			{#if invoice.needs_confirmation}<Button
					variant="secondary"
					disabled={busy}
					onclick={() => (mode = 'DISPUTE')}>Dispute</Button
				>{/if}
			<Button variant="secondary" disabled={busy} onclick={() => (mode = 'CORRECT')}
				>Propose correction</Button
			>
		</div>
		{#if mode === 'DISPUTE'}<form
				class="flex flex-wrap items-end gap-3"
				onsubmit={(e) => {
					e.preventDefault();
					decide('DISPUTE');
				}}
			>
				<label
					>Dispute reason<select bind:value={reason}
						><option value="WRONG_AMOUNT">Wrong amount</option><option value="NOT_RECOGNISED"
							>Not recognised</option
						><option value="ALREADY_PAID">Already paid</option><option value="GOODS_NOT_RECEIVED"
							>Goods not received</option
						><option value="OTHER">Other</option></select
					></label
				>
				<Button type="submit" loading={busy}>Save dispute</Button><Button
					variant="link"
					onclick={() => (mode = null)}>Cancel</Button
				>
			</form>{:else if mode === 'CORRECT'}<form
				class="flex flex-wrap items-end gap-3"
				onsubmit={(e) => {
					e.preventDefault();
					decide('CORRECT');
				}}
			>
				<label
					>New amount<input
						inputmode="decimal"
						bind:value={amount}
						placeholder="Leave unchanged"
					/></label
				>
				<label
					>New outstanding<input
						inputmode="decimal"
						bind:value={outstanding}
						placeholder="Leave unchanged"
					/></label
				>
				<label>New due date<input type="date" bind:value={due} /></label>
				<Button type="submit" loading={busy}>Save new version</Button><Button
					variant="link"
					onclick={() => (mode = null)}>Cancel</Button
				>
			</form>{/if}
		{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}
		{#if success}<p role="status">{success}</p>{/if}
	</div>
{/if}
