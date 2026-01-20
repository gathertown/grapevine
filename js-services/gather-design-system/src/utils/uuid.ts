import { v4 } from 'uuid';

export type Uuid = string & { __uuid: never };

// eslint-disable-next-line @typescript-eslint/consistent-type-assertions
export const uuid = () => v4() as Uuid;
