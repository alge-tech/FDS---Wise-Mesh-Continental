import { describe, expect, it } from 'vitest';
import { ApiError, createApiClient, isApiError, newIdempotencyKey, unwrap } from './client';

function recordingClient(respond: (request: Request) => Response) {
	const requests: Request[] = [];
	const client = createApiClient({
		baseUrl: 'http://mesh.test',
		fetch: async (request) => {
			requests.push(request);
			return respond(request);
		}
	});
	return { client, requests };
}

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
	new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json', ...headers }
	});

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('api client headers', () => {
	it('adds X-Requested-With and a fresh Idempotency-Key to non-GET requests', async () => {
		const { client, requests } = recordingClient(() => new Response(null, { status: 204 }));
		await client.POST('/v1/auth/logout');
		await client.POST('/v1/auth/logout');
		const [first, second] = requests;
		expect(first.headers.get('X-Requested-With')).toBe('mesh-web');
		expect(first.headers.get('Idempotency-Key')).toMatch(UUID);
		expect(second.headers.get('Idempotency-Key')).not.toBe(first.headers.get('Idempotency-Key'));
		expect(first.credentials).toBe('same-origin');
	});

	it('keeps a caller-supplied Idempotency-Key', async () => {
		const { client, requests } = recordingClient(() => new Response(null, { status: 204 }));
		await client.POST('/v1/auth/logout', { headers: { 'Idempotency-Key': 'retry-key-1' } });
		expect(requests[0].headers.get('Idempotency-Key')).toBe('retry-key-1');
	});

	it('leaves GET requests alone', async () => {
		const { client, requests } = recordingClient(() => json({ items: [] }));
		await client.GET('/v1/currencies');
		expect(requests[0].headers.has('X-Requested-With')).toBe(false);
		expect(requests[0].headers.has('Idempotency-Key')).toBe(false);
	});
});

describe('unwrap', () => {
	it('returns data on success', async () => {
		const items = [{ code: 'EUR', exponent: 2, name: 'Euro' }];
		const { client } = recordingClient(() => json({ items }));
		await expect(unwrap(client.GET('/v1/currencies'))).resolves.toEqual({ items });
	});

	it('resolves 204 responses', async () => {
		const { client } = recordingClient(() => new Response(null, { status: 204 }));
		await expect(unwrap(client.POST('/v1/auth/logout'))).resolves.toBeUndefined();
	});

	it('throws a typed ApiError from the error envelope', async () => {
		const { client } = recordingClient(() =>
			json(
				{
					error: {
						code: 'INVALID_CREDENTIALS',
						message: 'Email or password is wrong',
						correlation_id: 'corr-1',
						details: { field: 'password' }
					}
				},
				401
			)
		);
		const error = await unwrap(
			client.POST('/v1/auth/login', { body: { email: 'a@b.test', password: 'x' } })
		).catch((e: unknown) => e);
		expect(error).toBeInstanceOf(ApiError);
		expect(isApiError(error, 'INVALID_CREDENTIALS')).toBe(true);
		expect(error).toMatchObject({
			status: 401,
			code: 'INVALID_CREDENTIALS',
			message: 'Email or password is wrong',
			correlationId: 'corr-1',
			details: { field: 'password' }
		});
	});

	it('falls back to HTTP_<status> and the correlation header for non-envelope errors', async () => {
		const { client } = recordingClient(
			() =>
				new Response('upstream down', {
					status: 502,
					statusText: 'Bad Gateway',
					headers: { 'X-Correlation-ID': 'corr-502' }
				})
		);
		const error = await unwrap(client.GET('/v1/me')).catch((e: unknown) => e);
		expect(error).toMatchObject({ status: 502, code: 'HTTP_502', correlationId: 'corr-502' });
	});

	it('wraps network failures', async () => {
		const client = createApiClient({
			baseUrl: 'http://mesh.test',
			fetch: () => Promise.reject(new TypeError('fetch failed'))
		});
		const error = await unwrap(client.GET('/v1/me')).catch((e: unknown) => e);
		expect(error).toMatchObject({ status: 0, code: 'NETWORK_ERROR' });
	});
});

describe('newIdempotencyKey', () => {
	it('returns v4 UUIDs', () => {
		expect(newIdempotencyKey()).toMatch(UUID);
	});
});
