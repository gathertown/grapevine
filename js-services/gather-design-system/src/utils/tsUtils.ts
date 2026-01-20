export type ObjectKeys<T extends object> = `${Exclude<keyof T, symbol>}`;

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const objectKeys = Object.keys as <Type extends object>(
  value: Type
) => Array<ObjectKeys<Type>>;

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const objectValues = Object.values as <Type extends Record<PropertyKey, unknown>>(
  value: Type
) => Array<Type[keyof Type]>;

export const objectFromEntries = <K extends PropertyKey, V>(
  entries: Array<[K, V]>
): Record<K, V> => {
  // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
  const obj = {} as Record<K, V>;
  for (const [key, value] of entries) {
    obj[key] = value;
  }
  return obj;
};
