import { queryOptions } from '@tanstack/svelte-query';
import { api, ApiError, unwrap } from './client';
import { queryClient } from './query-client';
import type { LoginRequest, Me, PersonaList } from './types';

export const queryKeys = {
	me: ['me'],
	member: ['members', 'me'],
	currencies: ['currencies'],
	rates: ['rates'],
	personas: ['demo', 'personas']
} as const;

/** The signed-in user, or null when there is no session (401). */
export async function fetchMe(): Promise<Me | null> {
	try {
		return await unwrap(api.GET('/v1/me'));
	} catch (error) {
		if (error instanceof ApiError && error.status === 401) return null;
		throw error;
	}
}

export const meQueryOptions = () =>
	queryOptions({ queryKey: queryKeys.me, queryFn: fetchMe, staleTime: 30_000 });

export const memberQueryOptions = () =>
	queryOptions({
		queryKey: queryKeys.member,
		queryFn: () => unwrap(api.GET('/v1/members/me'))
	});

/** Currencies and their exponents change only with a deploy: load once per session. */
export const currenciesQueryOptions = () =>
	queryOptions({
		queryKey: queryKeys.currencies,
		queryFn: () => unwrap(api.GET('/v1/currencies')),
		staleTime: Infinity,
		gcTime: Infinity
	});

export const ratesQueryOptions = () =>
	queryOptions({
		queryKey: queryKeys.rates,
		queryFn: () => unwrap(api.GET('/v1/rates'))
	});

/** Demo personas, or null when demo mode is off (404 DEMO_MODE_OFF). */
export const personasQueryOptions = () =>
	queryOptions({
		queryKey: queryKeys.personas,
		queryFn: async (): Promise<PersonaList | null> => {
			try {
				return await unwrap(api.GET('/v1/demo/personas'));
			} catch (error) {
				if (error instanceof ApiError && error.status === 404) return null;
				throw error;
			}
		},
		staleTime: Infinity,
		retry: false
	});

export async function login(credentials: LoginRequest): Promise<Me> {
	const me = await unwrap(api.POST('/v1/auth/login', { body: credentials }));
	queryClient.clear();
	queryClient.setQueryData(queryKeys.me, me);
	return me;
}

export async function logout(): Promise<void> {
	try {
		await unwrap(api.POST('/v1/auth/logout'));
	} finally {
		queryClient.clear();
	}
}
