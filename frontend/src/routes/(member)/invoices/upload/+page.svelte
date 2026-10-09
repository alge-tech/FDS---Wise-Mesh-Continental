<script lang="ts">
	import { resolve } from '$app/paths';
	import { api, invoiceFormSchema, refreshMesh, uploadCsv } from '$lib/api/mesh';
	import type { components } from '$lib/api/schema';
	import { unwrap } from '$lib/api/client';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import InvoiceTable from '$lib/components/InvoiceTable.svelte';
	let { data } = $props();
	let file = $state<File | null>(null);
	let result = $state<components['schemas']['UploadResult'] | null>(null);
	let error = $state('');
	let busy = $state(false);
	let drag = $state(false);
	let tab = $state<'CSV' | 'MANUAL'>('CSV');
	let form = $state({
		invoice_number: '',
		issuer_tax_id: '',
		payer_tax_id: '',
		currency: 'EUR',
		amount: '',
		outstanding: '',
		issue_date: '2026-10-01',
		due_date: '2026-10-31'
	});
	function choose(selected?: File) {
		if (selected) {
			file = selected;
			result = null;
			error = '';
		}
	}
	async function upload() {
		if (!file) return;
		busy = true;
		error = '';
		result = null;
		try {
			if (file.size > 5 * 1024 * 1024) throw new Error('Choose a CSV smaller than 5 MB.');
			result = await uploadCsv(file);
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Upload failed.';
		} finally {
			busy = false;
		}
	}
	async function create() {
		const parsed = invoiceFormSchema.safeParse(form);
		if (!parsed.success) {
			error = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
			return;
		}
		busy = true;
		error = '';
		result = null;
		try {
			const invoice = await unwrap(api.POST('/v1/invoices', { body: parsed.data }));
			result = { items: [invoice], errors: [] };
			await refreshMesh();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not create invoice.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Add invoices · Wise Mesh</title></svelte:head>
<div class="flex flex-col gap-8">
	<PageHeader
		title="Add invoices"
		description={`Add invoices issued by or payable by ${data.member.name}. Amounts stay exact to the cent.`}
	/>
	<div class="flex gap-3">
		<Button
			variant={tab === 'CSV' ? 'primary' : 'secondary'}
			onclick={() => {
				tab = 'CSV';
				error = '';
			}}>Upload CSV</Button
		><Button
			variant={tab === 'MANUAL' ? 'primary' : 'secondary'}
			onclick={() => {
				tab = 'MANUAL';
				error = '';
			}}>Create one invoice</Button
		>
	</div>
	{#if tab === 'CSV'}<Card class="flex flex-col gap-5"
			><p>
				Use the template columns. Maximum 5 MB and 10,000 rows. Valid rows are accepted; rejected
				rows show the field to fix.
			</p>
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a class="self-start link-default" href="/v1/invoices/template.csv" download
				>Download CSV template</a
			>
			<label
				class={[
					'rounded-card border-2 border-dashed p-8 text-center',
					drag ? 'border-brand-forest bg-brand-pale' : 'border-content-tertiary'
				]}
				ondragover={(e) => {
					e.preventDefault();
					drag = true;
				}}
				ondragleave={() => (drag = false)}
				ondrop={(e) => {
					e.preventDefault();
					drag = false;
					choose(e.dataTransfer?.files[0]);
				}}
			>
				<span class="text-body-large-bold">{file?.name ?? 'Drop a CSV here or choose a file'}</span
				><input
					aria-label="CSV file"
					type="file"
					accept=".csv,text/csv"
					onchange={(e) => choose(e.currentTarget.files?.[0])}
				/>
			</label><Button loading={busy} disabled={!file} onclick={upload}>Upload invoices</Button>
		</Card>{:else}<Card
			><form
				class="grid gap-5 sm:grid-cols-2"
				onsubmit={(e) => {
					e.preventDefault();
					create();
				}}
			>
				<label
					>Invoice number<input bind:value={form.invoice_number} required maxlength="64" /></label
				><label
					>Currency<select bind:value={form.currency}
						>{#each ['EUR', 'USD', 'GBP', 'HUF', 'CNY'] as c (c)}<option>{c}</option>{/each}</select
					></label
				>
				<label
					>Issuer tax ID or registration number<input
						bind:value={form.issuer_tax_id}
						required
					/></label
				><label
					>Payer tax ID or registration number<input
						bind:value={form.payer_tax_id}
						required
					/></label
				>
				<label
					>Gross amount<input
						bind:value={form.amount}
						inputmode="decimal"
						placeholder="1250.00"
						required
					/></label
				><label
					>Outstanding amount<input
						bind:value={form.outstanding}
						inputmode="decimal"
						placeholder="Defaults to gross amount"
					/></label
				>
				<label>Issue date<input type="date" bind:value={form.issue_date} required /></label><label
					>Due date<input type="date" bind:value={form.due_date} required /></label
				><Button type="submit" loading={busy}>Create invoice</Button>
			</form></Card
		>{/if}
	{#if error}<p role="alert" class="text-sentiment-negative">{error}</p>{/if}
	{#if result}<p role="status" class="text-body-large-bold">
			{result.items.length} accepted · {result.errors.length} rejected
		</p>
		{#if result.items.length}<InvoiceTable items={result.items} /><Button
				href={resolve('/invoices')}
				variant="secondary">View invoices</Button
			>{/if}
		{#if result.errors.length}<div class="overflow-x-auto">
				<table class="w-full text-left">
					<thead><tr><th>Row</th><th>Field</th><th>Fix</th></tr></thead><tbody
						>{#each result.errors as e, index (index)}<tr class="border-t border-content-primary/10"
								><td>{e.row}</td><td>{e.field}</td><td>{e.reason}</td></tr
							>{/each}</tbody
					>
				</table>
			</div>{/if}{/if}
</div>
