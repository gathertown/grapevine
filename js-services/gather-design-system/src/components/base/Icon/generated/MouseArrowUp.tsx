import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMouseArrowUp = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M14.9999 4L11.9999 2L8.99994 4M11.9999 11.286V13.429M11.9999 22C9.05394 22 6.64294 19.589 6.64294 16.643V12.357C6.64294 9.411 9.05394 7 11.9999 7C14.9459 7 17.3569 9.411 17.3569 12.357V16.643C17.3569 19.589 14.9459 22 11.9999 22Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMouseArrowUp);
export default Memo;