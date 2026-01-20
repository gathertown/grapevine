import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgFlag = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M5 21V3.93M19 14.02V4C19 4 18.125 4.727 15.5 4.727C12.875 4.727 11.125 3 8.5 3C5.875 3 5 3.932 5 3.932M5 14C5 14 5.875 13.273 8.5 13.273C11.125 13.273 12.875 15 15.5 15C18.125 15 19 14.023 19 14.023" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgFlag);
export default Memo;