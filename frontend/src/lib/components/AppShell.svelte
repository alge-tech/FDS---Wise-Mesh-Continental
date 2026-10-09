<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { DropdownMenu } from 'bits-ui';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import LogOut from '@lucide/svelte/icons/log-out';
	import { logout } from '$lib/api/queries';
	import type { Me } from '$lib/api/types';
	import { roleLabel } from '$lib/auth';
	import { isActive, visibleNav, type NavItem } from '$lib/nav';
	import BrandLogo from './BrandLogo.svelte';
	import NotificationBell from './NotificationBell.svelte';

	interface Props {
		me: Me;
		nav: readonly NavItem[];
		/** Short area label shown next to the user, e.g. the member name or "Wise". */
		context: string;
		children: Snippet;
	}

	let { me, nav, context, children }: Props = $props();

	const items = $derived(visibleNav(nav, me));
	let loggingOut = $state(false);

	async function handleLogout() {
		loggingOut = true;
		try {
			await logout();
		} catch {
			// The login page re-checks the session, so a failed logout call is still safe to leave.
		} finally {
			loggingOut = false;
			await goto(resolve('/login'), { replaceState: true });
		}
	}
</script>

<div class="flex min-h-screen flex-col">
	<a
		href="#main"
		class="sr-only rounded-pill bg-brand-primary px-4 py-2 text-body-default-bold text-brand-forest focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
	>
		Skip to content
	</a>
	<header class="border-b border-content-primary/10 bg-background-screen">
		<div
			class="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-8 gap-y-2 px-6 py-3 xl:min-h-18 xl:flex-nowrap xl:gap-x-6 xl:py-0"
		>
			<BrandLogo />
			<nav
				aria-label="Main"
				class="order-last -mx-6 w-[calc(100%+3rem)] overflow-x-auto px-6 pb-1 xl:order-none xl:mx-0 xl:w-auto xl:min-w-0 xl:flex-1 xl:px-0 xl:py-1"
			>
				<ul class="flex w-max items-center gap-1">
					{#each items as item (item.href)}
						{@const active = isActive(item, page.url.pathname)}
						<li>
							<a
								href={resolve(item.href)}
								aria-current={active ? 'page' : undefined}
								class={[
									'inline-flex h-10 items-center rounded-pill px-4 text-body-default-bold whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-content-primary xl:px-3',
									active
										? 'bg-brand-pale text-brand-forest'
										: 'text-content-secondary hover:bg-background-neutral hover:text-content-primary'
								]}
							>
								{item.label}
							</a>
						</li>
					{/each}
				</ul>
			</nav>

			<div class="ml-auto flex shrink-0 items-center gap-2">
				{#if me.member}<NotificationBell />{/if}
				<DropdownMenu.Root>
					<DropdownMenu.Trigger
						class="inline-flex h-10 max-w-full shrink-0 items-center gap-2 rounded-pill border border-content-primary/15 px-4 text-left text-body-default-bold whitespace-nowrap text-content-primary hover:bg-content-primary/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-content-primary"
						aria-label={`Account menu for ${me.display_name}`}
					>
						<span class="truncate">{me.display_name}</span>
						<span
							class="hidden truncate text-body-default text-content-tertiary sm:inline xl:hidden"
							>{context}</span
						>
						<ChevronDown class="size-4 shrink-0" aria-hidden="true" />
					</DropdownMenu.Trigger>
					<DropdownMenu.Portal>
						<DropdownMenu.Content
							align="end"
							sideOffset={8}
							class="z-50 min-w-[240px] rounded-card bg-background-screen p-2 ring-1 ring-content-primary/10"
						>
							<div class="flex flex-col px-3 py-2">
								<span class="text-body-default-bold text-content-primary">{me.display_name}</span>
								<span class="text-body-default text-content-tertiary">{me.email}</span>
								<span class="text-body-default text-content-tertiary">
									{roleLabel(me.role)} · {context}
								</span>
							</div>
							<DropdownMenu.Separator class="my-1 h-px bg-content-primary/10" />
							<DropdownMenu.Item
								onSelect={handleLogout}
								disabled={loggingOut}
								class="flex h-10 cursor-pointer items-center gap-2 rounded-pill px-3 text-body-default-bold text-content-primary outline-none data-highlighted:bg-background-neutral"
							>
								<LogOut class="size-4" aria-hidden="true" />
								Log out
							</DropdownMenu.Item>
						</DropdownMenu.Content>
					</DropdownMenu.Portal>
				</DropdownMenu.Root>
			</div>
		</div>
	</header>

	<main id="main" class="mx-auto w-full max-w-[1200px] min-w-0 flex-1 px-6 py-8">
		{@render children()}
	</main>
</div>
