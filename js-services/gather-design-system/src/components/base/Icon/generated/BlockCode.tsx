import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgBlockCode = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M15.8944 3.00002L16.9999 3.00002C18.6569 3.00002 19.9999 4.34302 19.9999 6.00002L19.9999 16.056C19.9999 17.713 18.6569 19.056 16.9999 19.056L5.99988 19.056C4.34288 19.056 2.99988 17.713 2.99988 16.056L2.99988 12.8364M3.60372 7.65584L1.56372 5.61584L3.60372 3.57581M10.4067 7.65785L12.4477 5.61585L10.4067 3.57385M7.93373 2.11584L6.07373 9.11584" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgBlockCode);
export default Memo;