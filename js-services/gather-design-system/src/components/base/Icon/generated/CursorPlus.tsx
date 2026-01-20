import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgCursorPlus = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M16 4V10M19 7H13M13.833 17.009H9.658L6.984 19.66C6.249 20.389 5 19.868 5 18.833V8.176C5 7.139 6.254 6.619 6.988 7.353L14.657 15.022C15.39 15.755 14.871 17.009 13.833 17.009Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgCursorPlus);
export default Memo;