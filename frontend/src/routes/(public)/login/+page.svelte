<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { createMutation, createQuery } from '@tanstack/svelte-query';
	import { z } from 'zod';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import { ApiError } from '$lib/api/client';
	import { login, personasQueryOptions } from '$lib/api/queries';
	import type { LoginRequest, Me, Persona } from '$lib/api/types';
	import { roleLabel, safeNextPath } from '$lib/auth';
	import Button from '$lib/components/Button.svelte';
	import Card from '$lib/components/Card.svelte';
	import Section from '$lib/components/Section.svelte';
	import TextField from '$lib/components/TextField.svelte';

	// Mirrors the API's LoginRequest; the API stays the source of truth.
	const loginSchema = z.object({
		email: z.email({ error: 'Enter a valid email address' }),
		password: z.string().min(1, { error: 'Enter your password' })
	});
	type Field = keyof z.infer<typeof loginSchema>;

	let email = $state('');
	let password = $state('');
	let fieldErrors = $state<Partial<Record<Field, string>>>({});
	let activePersona = $state<string | null>(null);

	const personas = createQuery(() => personasQueryOptions());

	// Personas grouped by member, in the order the API lists them; Wise staff have no member.
	const groups = $derived.by(() => {
		const result: { name: string; personas: Persona[] }[] = [];
		for (const persona of personas.data?.items ?? []) {
			const name = persona.member_name ?? 'Wise';
			const group = result.find((g) => g.name === name);
			if (group) group.personas.push(persona);
			else result.push({ name, personas: [persona] });
		}
		return result;
	});

	const loginMutation = createMutation(() => ({
		mutationFn: (credentials: LoginRequest) => login(credentials),
		onSuccess: (me: Me) => {
			const target = safeNextPath(page.url.searchParams.get('next'), me.role);
			// `target` is a runtime-validated same-origin path (safeNextPath), so resolve()'s
			// per-route typing cannot apply; the app has no base path.
			// eslint-disable-next-line svelte/no-navigation-without-resolve
			return goto(target, { replaceState: true });
		},
		onSettled: () => {
			activePersona = null;
		}
	}));

	const formError = $derived.by(() => {
		const error = loginMutation.error;
		if (!error) return null;
		if (error instanceof ApiError) {
			if (error.code === 'INVALID_CREDENTIALS') return 'That email and password do not match.';
			if (error.code === 'RATE_LIMITED') return 'Too many attempts. Wait a minute, then try again.';
			return error.message;
		}
		return 'Something went wrong. Try again.';
	});

	function submit(credentials: { email: string; password: string }) {
		const result = loginSchema.safeParse(credentials);
		if (!result.success) {
			const errors: Partial<Record<Field, string>> = {};
			for (const issue of result.error.issues) {
				const field = issue.path[0] as Field;
				errors[field] ??= issue.message;
			}
			fieldErrors = errors;
			return;
		}
		fieldErrors = {};
		loginMutation.mutate(result.data);
	}

	function onsubmit(event: SubmitEvent) {
		event.preventDefault();
		submit({ email, password });
	}

	function usePersona(persona: Persona) {
		if (!personas.data) return;
		email = persona.email;
		password = personas.data.password;
		activePersona = persona.email;
		submit({ email, password });
	}
</script>

<svelte:head><title>Log in · Wise Mesh</title></svelte:head>

<div
	class="grid grid-cols-1 items-start gap-8 pt-6 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)] lg:gap-12 lg:pt-12"
>
	<Card class="flex flex-col gap-6">
		<div class="flex flex-col gap-1">
			<h1 class="text-screen-title text-content-primary">Log in to Mesh</h1>
			<p class="text-body-default text-content-secondary">
				Use your Wise Business email and password.
			</p>
		</div>

		{#if formError}
			<div
				role="alert"
				class="flex items-start gap-3 rounded-card bg-background-neutral p-4 text-body-default text-content-primary"
			>
				<CircleAlert class="mt-0.5 size-4 shrink-0 text-sentiment-negative" aria-hidden="true" />
				<p>{formError}</p>
			</div>
		{/if}

		<form class="flex flex-col gap-4" novalidate {onsubmit}>
			<TextField
				label="Email"
				name="email"
				type="email"
				autocomplete="username"
				required
				bind:value={email}
				error={fieldErrors.email}
			/>
			<TextField
				label="Password"
				name="password"
				type="password"
				autocomplete="current-password"
				required
				bind:value={password}
				error={fieldErrors.password}
			/>
			<Button type="submit" size="lg" fullWidth loading={loginMutation.isPending}>Log in</Button>
		</form>

		<p class="text-body-default text-content-tertiary">
			New to Mesh? Members join through Wise. <a href={resolve('/')} class="link-default"
				>Learn how netting works</a
			>
		</p>
	</Card>

	{#if personas.data}
		<Section title="Demo personas">
			<p class="text-body-default text-content-secondary">
				Demo mode is on. Pick a persona to log in with its seeded account.
			</p>
			<div class="flex flex-col gap-4">
				{#each groups as group (group.name)}
					<Card class="flex flex-col gap-3">
						<h3 class="text-body-large-bold text-content-primary">{group.name}</h3>
						<ul class="flex min-w-0 flex-wrap gap-2">
							{#each group.personas as persona (persona.email)}
								<li>
									<Button
										variant="secondary"
										size="sm"
										loading={loginMutation.isPending && activePersona === persona.email}
										disabled={loginMutation.isPending && activePersona !== persona.email}
										onclick={() => usePersona(persona)}
										aria-label={`Log in as ${persona.display_name}, ${roleLabel(persona.role)}${persona.member_name ? `, ${persona.member_name}` : ''}`}
									>
										{persona.display_name}
										<span class="text-body-default text-content-tertiary">
											{roleLabel(persona.role)}
										</span>
									</Button>
								</li>
							{/each}
						</ul>
					</Card>
				{/each}
			</div>
		</Section>
	{/if}
</div>
