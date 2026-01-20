import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserCheck = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M3.99664 20.0034C3.99664 17.5173 6.01248 15.5015 8.49852 15.5015H11.0826M19.0029 16.9401L16.0017 19.9413L14.2019 18.1406M16.2518 8.24848C16.2518 10.5967 14.3482 12.5002 12 12.5002C9.6518 12.5002 7.74821 10.5967 7.74821 8.24848C7.74821 5.90029 9.6518 3.9967 12 3.9967C14.3482 3.9967 16.2518 5.90029 16.2518 8.24848Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserCheck);
export default Memo;