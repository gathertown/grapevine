import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgSliders = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5.70123 20.254V14.0015M5.70123 10.25V3.74707M11.9998 20.0038V12.7505M11.9998 8.99915V3.99707M18.2984 20.2536V16.002M18.2984 12.2508V3.74707M3.74609 13.7515H7.74982M9.99982 9.24902H13.9998M16.2498 15.752H20.2498" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgSliders);
export default Memo;