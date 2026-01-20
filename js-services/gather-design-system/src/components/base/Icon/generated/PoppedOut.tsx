import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPoppedOut = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M8 14H4.385C3.62 14 3 13.38 3 12.615V4.385C3 3.62 3.62 3 4.385 3H18.616C19.38 3 20 3.62 20 4.385V9M19 21H14C12.895 21 12 20.105 12 19V15C12 13.895 12.895 13 14 13H19C20.105 13 21 13.895 21 15V19C21 20.105 20.105 21 19 21Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgPoppedOut);
export default Memo;