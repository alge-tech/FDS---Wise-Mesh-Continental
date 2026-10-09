import createClient, { type Client, type Middleware } from 'openapi-fetch';
import { z } from 'zod';
import type { paths } from './schema';

/** Error envelope every API failure uses: {"error": {code, message, correlation_id, details}}. */
export const errorEnvelopeSchema = z.object({
	error: z.object({
		code: z.string(),
		message: z.string(),
		correlation_id: z.string().nullish(),
		details: z.record(z.string(), z.unknown()).nullish()
	})
});

export interface ApiErrorInit {
	status: number;
	code: string;
	message: string;
	correlationId?: string | null;
	details?: Record<string, unknown>;
	cause?: unknown;
}

/** A failed API call. `status` is 0 when the request never reached the API. */
export class ApiError extends Error {
	readonly status: number;
	readonly code: string;
	readonly correlationId: string | null;
	readonly details: Record<string, unknown>;

	constructor(init: ApiErrorInit) {
		super(init.message, { cause: init.cause });
		this.name = 'ApiError';
		this.status = init.status;
		this.code = init.code;
		this.correlationId = init.correlationId ?? null;
		this.details = init.details ?? {};
	}

	static fromResponse(response: Response, body: unknown): ApiError {
		const headerCorrelationId = response.headers.get('X-Correlation-ID');
		const parsed = errorEnvelopeSchema.safeParse(body);
		if (parsed.success) {
			const { code, message, correlation_id, details } = parsed.data.error;
			return new ApiError({
				status: response.status,
				code,
				message,
				correlationId: correlation_id ?? headerCorrelationId,
				details: details ?? {}
			});
		}
		return new ApiError({
			status: response.status,
			code: `HTTP_${response.status}`,
			message: response.statusText || 'The request failed',
			correlationId: headerCorrelationId,
			details: body && typeof body === 'object' ? { body } : {}
		});
	}

	static network(cause: unknown): ApiError {
		return new ApiError({
			status: 0,
			code: 'NETWORK_ERROR',
			message: 'Could not reach Mesh. Check your connection and try again.',
			cause
		});
	}
}

export function isApiError(error: unknown, code?: string): error is ApiError {
	return error instanceof ApiError && (code === undefined || error.code === code);
}

/** UUID v4 for Idempotency-Key. Falls back to getRandomValues outside secure contexts (LAN IPs). */
export function newIdempotencyKey(): string {
	if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
	const bytes = crypto.getRandomValues(new Uint8Array(16));
	bytes[6] = (bytes[6] & 0x0f) | 0x40;
	bytes[8] = (bytes[8] & 0x3f) | 0x80;
	const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
	return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/**
 * Every state-changing request carries the CSRF marker and an Idempotency-Key. Callers that retry
 * the same logical action pass their own key via `headers: { 'Idempotency-Key': key }`.
 */
export const meshHeadersMiddleware: Middleware = {
	onRequest({ request }) {
		if (!SAFE_METHODS.has(request.method.toUpperCase())) {
			request.headers.set('X-Requested-With', 'mesh-web');
			if (!request.headers.has('Idempotency-Key')) {
				request.headers.set('Idempotency-Key', newIdempotencyKey());
			}
		}
		return request;
	}
};

export interface ApiClientOptions {
	baseUrl?: string;
	fetch?: (request: Request) => Promise<Response>;
}

export function createApiClient(options: ApiClientOptions = {}): Client<paths> {
	const client = createClient<paths>({
		baseUrl: options.baseUrl ?? '',
		credentials: 'same-origin',
		...(options.fetch ? { fetch: options.fetch } : {})
	});
	client.use(meshHeadersMiddleware);
	return client;
}

/** Same-origin client: Vite (dev) or nginx (compose) proxies /v1 to the API. */
export const api = createApiClient();

interface ApiResult<T> {
	data?: T;
	error?: unknown;
	response: Response;
}

/**
 * Await an openapi-fetch call and return its data, or throw ApiError.
 * `await unwrap(api.GET('/v1/me'))` → Me.
 */
export async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
	let result: ApiResult<T>;
	try {
		result = await request;
	} catch (cause) {
		throw ApiError.network(cause);
	}
	if (!result.response.ok) {
		throw ApiError.fromResponse(result.response, result.error);
	}
	return result.data as T;
}
