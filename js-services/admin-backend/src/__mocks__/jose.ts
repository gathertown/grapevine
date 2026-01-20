/* eslint-disable @typescript-eslint/no-explicit-any, no-undef */
export const jwtVerify = jest.fn();
export const importJWK = jest.fn();
export interface JWTPayload {
  [propName: string]: any;
}
export interface JWK {
  [propName: string]: any;
}
