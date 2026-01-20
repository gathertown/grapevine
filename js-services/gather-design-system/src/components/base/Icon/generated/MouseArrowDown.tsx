import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgMouseArrowDown = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8.99994 20L11.9999 22L14.9999 20M11.9999 6.286V8.429M11.9999 17C9.05394 17 6.64294 14.589 6.64294 11.643V7.357C6.64294 4.411 9.05394 2 11.9999 2C14.9459 2 17.3569 4.411 17.3569 7.357V11.643C17.3569 14.589 14.9459 17 11.9999 17Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgMouseArrowDown);
export default Memo;