/** Display API UTC timestamps in the browser's local timezone. */
export function localTime(timestamp: string): string {
	return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(
		new Date(timestamp)
	);
}
