<script lang="ts">
	import EmptyState from './EmptyState.svelte';
	import PageHeader from './PageHeader.svelte';

	interface Props {
		title: string;
		/** What this screen will hold, from the PRD route table. */
		description: string;
		milestone?: string;
	}

	let { title, description, milestone }: Props = $props();
</script>

<div class="flex flex-col gap-8">
	<PageHeader {title} {description} />
	<EmptyState
		title="Coming in a later milestone"
		description={milestone
			? `This screen is planned for ${milestone}.`
			: 'This screen is not built yet.'}
	/>
</div>
