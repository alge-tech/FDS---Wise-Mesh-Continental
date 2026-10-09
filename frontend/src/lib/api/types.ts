/**
 * Convenience aliases derived from the generated `paths`, so they survive `bun run gen:api`
 * even if the backend renames its Pydantic models.
 */
import type { paths } from './schema';

type JsonBody<T> = T extends { content: { 'application/json': infer B } } ? B : never;
type Ok<Op> = Op extends { responses: { 200: infer R } } ? JsonBody<R> : never;
type RequestJson<Op> = Op extends { requestBody?: infer B } ? JsonBody<NonNullable<B>> : never;

export type Me = Ok<paths['/v1/me']['get']>;
export type MeMember = NonNullable<Me['member']>;
export type MemberDetail = Ok<paths['/v1/members/me']['get']>;
export type Balance = MemberDetail['balances'][number];
export type MoneyDto = MemberDetail['payable_limit'];
export type CurrencyList = Ok<paths['/v1/currencies']['get']>;
export type Currency = CurrencyList['items'][number];
export type RateList = Ok<paths['/v1/rates']['get']>;
export type Rate = RateList['items'][number];
export type PersonaList = Ok<paths['/v1/demo/personas']['get']>;
export type Persona = PersonaList['items'][number];
export type LoginRequest = RequestJson<paths['/v1/auth/login']['post']>;
export type ApiRole = Me['role'];
