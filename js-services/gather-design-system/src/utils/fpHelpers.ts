import { both, complement, is, isEmpty, reject, trim } from 'ramda';

export const isNil = (value: unknown): value is null | undefined => value == null;

export const isNotNil = <T>(value: T | null | undefined): value is T => value != null;

export const isNotEmpty = complement(isEmpty);

export const isNotNilAndNotEmpty = <T>(x: T | undefined | null): x is T =>
  both(isNotNil, isNotEmpty)(x);

export const isNilOrEmpty = (x: unknown): x is undefined | null | Record<string, never> | [] | '' =>
  !isNotNilAndNotEmpty(x);

export const isArray = <T>(arg: unknown): arg is readonly T[] => Array.isArray(arg);

export const isString = (value: unknown): value is string => typeof value === 'string';

export const isBlank = <T>(x: T): boolean =>
  is(String, x)
    ? isNotNilAndEmpty(trim(x))
    : is(Boolean, x)
      ? !x
      : x === undefined || x === null
        ? true
        : isNotNilAndEmpty(x);

const isNotNilAndEmpty = <T>(x: T | undefined | null): x is T => both(isNotNil, isEmpty)(x);

export function compact<T>(x: readonly T[]): Exclude<T, null | undefined | false>[];
export function compact<T>(
  x: Record<string, T>
): Record<string, Exclude<T, null | undefined | false>>;
export function compact<T>(xs: readonly T[] | Record<string, T>): readonly T[] | Record<string, T> {
  return reject((x) => x === false || isNil(x), xs);
}

function assertNotNil<T>(x: T | null | undefined, message?: string): asserts x is T {
  if (x == null) throw new Error(message ?? 'Expected something, got nothing');
}

export const just = <T>(
  x?: T | null,
  message = 'Expected something, got nothing'
): NonNullable<T> => {
  assertNotNil(x, message);
  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
  return x as NonNullable<T>;
};

export const doIt = <T>(fn: () => T): T => fn();

export const maybeReturnProps = <T extends Record<string, unknown>>(
  condition: boolean,
  props: T
): {} => (condition ? props : {});
