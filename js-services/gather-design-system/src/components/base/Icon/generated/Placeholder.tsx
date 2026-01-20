import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgPlaceholder = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M18.5408 5.45927C22.1531 9.07162 22.1531 14.9284 18.5408 18.5407C14.9284 22.1531 9.07165 22.1531 5.45932 18.5407C1.84696 14.9284 1.84696 9.0716 5.45932 5.45927C9.07167 1.84691 14.9285 1.84691 18.5408 5.45927Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgPlaceholder);
export default Memo;