import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserArrowRight = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M17 20C17 17.544 15.009 15.553 12.553 15.553H7.447C4.991 15.553 3 17.544 3 20M17 12H22M22 12L20 10M22 12L20 14M5.75 8.25C5.75 10.5972 7.65279 12.5 10 12.5C12.3472 12.5 14.25 10.5972 14.25 8.25C14.25 5.90279 12.3472 4 10 4C7.65279 4 5.75 5.90279 5.75 8.25Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserArrowRight);
export default Memo;