// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		interface Error {
			message: string;
			/** API error code when the failure came from the API, e.g. FORBIDDEN. */
			code?: string;
			/** Correlation ID to quote when reporting the problem. */
			correlationId?: string | null;
		}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
